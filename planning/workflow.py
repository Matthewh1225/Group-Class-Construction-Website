import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import RLock

import httpx
from google.genai.errors import APIError as GeminiAPIError
from groq import APIError as GroqAPIError
from openrouter.errors import OpenRouterError, NoResponseError, ResponseValidationError
from pydantic import ValidationError

from . import ai_config
from .ai_planner import ask_model, check_model
from .follow_up import MAX_QUESTIONS, pending_questions, unresolved_questions
from .jobs import pro_access_allowed, round_attempts
from .schemas import Estimate, Specification, check_estimate


class StageError(Exception):
    pass


class InvalidOutput(ValueError):
    pass


def stage_error(error):
    code = getattr(error, "status_code", None) or getattr(error, "code", None)
    if code == 429:
        return "Provider rate limit reached (HTTP 429)", True
    if code in {401, 403, 404}:
        return f"Provider access/model unavailable (HTTP {code})", False
    if code == 400:
        # Groq explains the problem in error.body["error"]["message"]
        message = ""
        body = getattr(error, "body", None)
        if isinstance(body, dict):
            details = body.get("error", body)
            if isinstance(details, dict):
                message = details.get("message", "")
        if "max completion tokens reached" in message.lower():
            return "Provider ran out of output tokens while building the JSON estimate", True
        return "Provider rejected the request or structured output (HTTP 400)", True
    if isinstance(code, int) and code >= 500:
        return f"Provider service unavailable (HTTP {code})", True
    if isinstance(error, (ValidationError, json.JSONDecodeError)):
        return "Provider output did not match the required JSON schema", True
    if isinstance(error, ValueError):
        return str(error), True
    # the exception name (for example ReadTimeout) is kept to help debugging
    return f"Provider request failed or timed out ({type(error).__name__})", True


def validate_stage_response(response, record_type, validate):
    if response["status"] != "completed":
        raise InvalidOutput("Provider output was truncated, blocked or incomplete.")
    output = record_type.model_validate_json(response["text"])
    if validate is not None:
        try:
            validate(output)
        except ValueError as error:
            # Calculation validation uses ValueError for invalid model-supplied inputs.
            raise InvalidOutput(str(error)) from error
    return output


def retry_delay(error, retryable, has_fallback):
    if has_fallback:
        # A configured fallback takes precedence over the failed provider's limits.
        return 0
    if not retryable:
        return None
    headers = getattr(error, "headers", None)
    if headers is None:
        response = getattr(error, "response", None)
        headers = getattr(response, "headers", {}) or {}
    try:
        delay = float(headers.get("retry-after", 1))
    except (TypeError, ValueError):
        delay = 1
    if delay < 0 or delay > 30:
        return None
    return delay


def pick_model(role_settings, for_retry):
    # The role's own model is used first.
    # A fallback (Pro's auditor has one) is used for the retry, or straight away when the role's own model is not configured.
    choices = [role_settings["model"]]
    if "fallback" in role_settings:
        if for_retry:
            choices = [role_settings["fallback"], role_settings["model"]]
        else:
            choices = [role_settings["model"], role_settings["fallback"]]
    problem = None
    for model_name in choices:
        try:
            check_model(model_name, role_settings["reasoning"])
            return model_name
        except ValueError as error:
            problem = error
    raise StageError(str(problem))


def run_stage(job, name, role, record_type, inputs, instructions, checkpoint, validate=None, state_lock=None):
    # Each try is recorded in job["attempts"] and saved before the provider is called, so a crash still counts it towards the round's attempt limit.
    # The second try is told what went wrong and, when the role has one, uses the fallback model.
    state_lock = state_lock or RLock()
    settings = ai_config.WORKFLOW_TIERS[job["tier"]]
    role_settings = settings[role]
    reasoning = role_settings["reasoning"]
    output_tokens = role_settings["output_tokens"]
    schema = record_type.model_json_schema()

    # Reuse completed stages after a retry or crash.
    # New answers start a new specification version, so results from the earlier version are not reused.
    saved = job["stages"].get(name)
    if saved is not None and saved.get("specification_version") == job["specification_version"]:
        return record_type.model_validate(saved["output"])

    last_error = None
    for try_number in (1, 2):
        is_retry = try_number == 2
        model_name = pick_model(role_settings, for_retry=is_retry)
        request_inputs = inputs
        if is_retry:
            request_inputs = {**inputs, "recovery_feedback": last_error}
        prompt = json.dumps(request_inputs, ensure_ascii=False, allow_nan=False)

        with state_lock:
            # only this round counts; earlier rounds are kept as history
            if len(round_attempts(job)) >= settings["max_attempts"]:
                raise StageError("The job has reached its provider attempt limit.")
            attempt = {"name": name, "model": model_name, "reasoning": reasoning,
                       "specification_version": job["specification_version"],
                       "try": try_number, "status": "started", "started_at": time.time()}
            if model_name != role_settings["model"]:
                attempt["fallback_for"] = role_settings["model"]
            job["attempts"].append(attempt)
            checkpoint(job)

        try:
            response = ask_model(model_name, prompt, reasoning, instructions, schema, output_tokens)
            with state_lock:
                # Keep the token counts and timing even when the response fails validation.
                usage = dict(response)
                usage.pop("text", None)
                attempt["usage"] = usage
            output = validate_stage_response(response, record_type, validate)
        except (GeminiAPIError, GroqAPIError, OpenRouterError, NoResponseError,
                ResponseValidationError, httpx.TransportError, TimeoutError, ConnectionError,
                ValidationError, json.JSONDecodeError, InvalidOutput) as error:
            last_error, retryable = stage_error(error)
            with state_lock:
                attempt["status"] = "failed"
                attempt["error"] = last_error
                checkpoint(job)
            if is_retry:
                break
            delay = retry_delay(error, retryable, has_fallback="fallback" in role_settings)
            if delay is None:
                break
            time.sleep(delay)
        else:
            with state_lock:
                attempt["status"] = "completed"
                job["stages"][name] = {"specification_version": job["specification_version"],
                                       "output": output.model_dump()}
                checkpoint(job)
            return output

    raise StageError(f"{name}: {last_error}.")


def independent_plans(job, inputs, checkpoint):
    # Both threads change the same job, so they share one lock and only one of them updates or saves it at a time.
    lock = RLock()
    with ThreadPoolExecutor(max_workers=2) as executor:
        primary = executor.submit(
            run_stage, job, "primary_initial", "planner", Estimate, inputs,
            ai_config.PLANNER_PROMPT, checkpoint, check_estimate, lock,
        )
        secondary = executor.submit(
            run_stage, job, "secondary_initial", "second_planner", Estimate, inputs,
            ai_config.PLANNER_PROMPT, checkpoint, check_estimate, lock,
        )
        # result() waits for a planner and raises its error if it failed.
        # Leaving the "with" block always waits for both, so a failure never cuts the other short.
        return {"primary": primary.result().model_dump(),
                "secondary": secondary.result().model_dump()}


def ask_questions(job, questions, checkpoint):
    # Returns True when the job is now waiting for the user.
    # Questions that are not asked stay in the saved estimate and appear as details needing confirmation.
    if job.get("answers"):
        # The user already answered a round: plan with assumptions instead of asking again.
        return False
    questions = pending_questions(questions, [])[:MAX_QUESTIONS]
    if not questions:
        return False
    job["questions"] = []
    for number, question in enumerate(questions, 1):
        job["questions"].append({"id": f"Q{number}", "question": question})
    job["status"] = "needs_input"
    job["phase"] = "Project details needed"
    checkpoint(job)
    return True


def finish_plan(job, estimate, estimates, checkpoint):
    # A validated estimate is complete when every material has a quantity and nothing is left to confirm.
    # Advisory warnings (assumptions, safety notes) are still shown, but they do not turn a finished estimate into a partial one.
    # "degraded" means a fallback model finished a stage in this round
    degraded = False
    for attempt in round_attempts(job):
        if attempt.get("fallback_for") and attempt["status"] == "completed":
            degraded = True
    warnings = list(estimate.warnings)
    if degraded:
        warnings.append("The planned reviewer was unavailable, so a fallback model reviewed this estimate.")
    # The materials table already labels manual and unknown quantities, so they are not repeated as warnings here.
    unknown_quantity = any(material.quantity is None for material in estimate.materials)
    questions = unresolved_questions(estimate.questions, job.get("answers", []))
    partial = bool(questions) or unknown_quantity
    if partial:
        planning_status = "partial"
    else:
        planning_status = "complete"
    job["result"] = {
        "tier": job["tier"],
        "planning_status": planning_status,
        "estimate": estimate.model_dump(), "warnings": warnings,
        "independent_estimates": estimates, "review_process_degraded": degraded,
    }
    if not ask_questions(job, questions, checkpoint):
        job["questions"] = []
        job["status"] = planning_status
        if partial:
            job["phase"] = "Review needed"
        else:
            job["phase"] = "Complete"
        checkpoint(job)
    return job


def run_workflow(job, checkpoint):
    if job["config_version"] != ai_config.WORKFLOW_VERSION:
        raise StageError("This job uses an older format. Start a new job; saved results remain available.")
    if job["tier"] == "pro" and not pro_access_allowed(job["owner"]):
        raise StageError(f"{ai_config.WORKFLOW_TIERS['pro']['label']} access is not enabled for this account.")

    job["phase"] = "Interpreting"
    checkpoint(job)
    specification = run_stage(
        job, "interpret", "interpreter", Specification,
        {"original_request": job["project"], "answers": job["answers"],
         "previous_specification": job.get("previous_specification")},
        ai_config.INTERPRETER_PROMPT, checkpoint,
    )
    job["specification"] = specification.model_dump()
    if ask_questions(job, specification.questions, checkpoint):
        return job

    inputs = {"original_request": job["project"], "answers": job["answers"],
              "details": job["specification"]}
    job["phase"] = "Planning"
    checkpoint(job)
    if job["tier"] == "pro":
        estimates = independent_plans(job, inputs, checkpoint)
        review_inputs = {**inputs, "estimates": estimates}
        review_prompt = ai_config.RECONCILER_PROMPT
    else:
        draft = run_stage(job, "plan", "planner", Estimate, inputs,
                          ai_config.PLANNER_PROMPT, checkpoint, check_estimate)
        estimates = {}
        review_inputs = {**inputs, "estimate": draft.model_dump()}
        review_prompt = ai_config.AUDITOR_PROMPT

    job["phase"] = "Reviewing"
    checkpoint(job)
    estimate = run_stage(job, "review", "auditor", Estimate, review_inputs,
                         review_prompt, checkpoint, check_estimate)
    return finish_plan(job, estimate, estimates, checkpoint)
