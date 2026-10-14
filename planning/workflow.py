"""Shared stage execution, recovery and the three planning policies."""

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import RLock

from pydantic import ValidationError

from . import ai_config
from .ai_planner import response_metadata, workflow_model, workflow_response
from .contracts import Estimate, Specification, check_estimate


class StageError(Exception):
    """An expected provider, validation or attempt-limit failure with a safe message."""


def stage_error(error):
    code = getattr(error, "status_code", None) or getattr(error, "code", None)
    if code == 429:
        return "Provider rate limit reached", "transport", True
    if code in {401, 403, 404}:
        return f"Provider access/model unavailable (HTTP {code})", "configuration", False
    if code == 400:
        body = getattr(error, "body", None)
        details = body.get("error", body) if isinstance(body, dict) else {}
        message = details.get("message", "") if isinstance(details, dict) else ""
        if "max completion tokens reached" in message.lower():
            return "Provider ran out of output tokens while building the JSON estimate", "output_limit", True
        return "Provider rejected the request or structured output", "schema", True
    if isinstance(code, int) and code >= 500:
        return f"Provider service unavailable (HTTP {code})", "transport", True
    if isinstance(error, (ValidationError, json.JSONDecodeError)):
        return "Provider output did not match the required JSON schema", "schema", True
    if isinstance(error, ValueError):
        return str(error), "schema", True
    return "Provider request failed or timed out", "transport", True


def call_and_validate_stage(alias, prompt, reasoning, instructions, schema,
                            output_tokens, record_type, validate, attempt, state_lock):
    """Make one provider request and validate its complete JSON response."""
    response = workflow_response(alias, prompt, reasoning, instructions, schema, output_tokens)
    with state_lock:
        attempt["metadata"] = response_metadata(response)
    if response["status"] != "completed":
        raise ValueError("Provider output was truncated, blocked or incomplete.")
    output = record_type.model_validate_json(response["text"])
    if validate is not None:
        validate(output)
    return output


def run_stage(job, name, role, record_type, inputs, instructions, checkpoint, validate=None, state_lock=None):
    state_lock = state_lock or RLock()
    settings = ai_config.WORKFLOW_TIERS[job["tier"]]
    output_tokens = settings.get(role + "_output_tokens", settings["output_tokens"])
    with state_lock:
        job["current_stage"] = name
    alias, reasoning = settings[role]
    try:
        model, _ = workflow_model(alias, reasoning)
    except ValueError as error:
        fallback = settings.get(role + "_fallback")
        if fallback is None:
            raise StageError(str(error)) from error
        alias, reasoning = fallback
        try:
            model, _ = workflow_model(alias, reasoning)
        except ValueError as fallback_error:
            raise StageError(str(fallback_error)) from fallback_error
    prompt = json.dumps(inputs, ensure_ascii=False, allow_nan=False)
    schema = record_type.model_json_schema()
    fingerprint = hashlib.sha256(
        json.dumps([job["config_version"], alias, model.get("model"), reasoning,
                    output_tokens, instructions, schema, inputs], sort_keys=True).encode()
    ).hexdigest()
    saved = job["stages"].get(name)
    if saved is not None:
        if saved["fingerprint"] != fingerprint:
            raise StageError("Saved stage inputs or configuration changed. Start a new job.")
        return record_type.model_validate(saved["output"])
    invocation = job.get("stage_invocations", {}).get(name, 1)
    previous_attempts = 0
    for attempt in job["attempts"]:
        if attempt["name"] == name and attempt["specification_version"] == job["specification_version"] and attempt.get("invocation", 1) == invocation:
            previous_attempts += 1
    for recovery in range(previous_attempts, 2):
        fallback = settings.get(role + "_fallback")
        if recovery and fallback:
            alias, reasoning = fallback
            try:
                model, _ = workflow_model(alias, reasoning)
            except ValueError as error:
                raise StageError(str(error)) from error
            if job["tier"] == "pro" and reasoning != "high":
                raise StageError("Pro recovery cannot lower reasoning.")
        request_prompt = prompt
        if recovery and job["attempts"]:
            recovery_inputs = inputs.copy()
            previous_error = "The preceding request did not produce valid output."
            for earlier in reversed(job["attempts"]):
                if earlier["name"] == name and earlier["specification_version"] == job["specification_version"]:
                    previous_error = earlier.get("error", previous_error)
                    break
            recovery_inputs["recovery_feedback"] = previous_error
            request_prompt = json.dumps(recovery_inputs, ensure_ascii=False, allow_nan=False)
        with state_lock:
            if len(job["attempts"]) >= settings["max_attempts"]:
                raise StageError("The job has reached its provider attempt limit.")
            attempt = {"name": name, "alias": alias, "requested_reasoning": reasoning,
                       "specification_version": job["specification_version"],
                       "prompt_version": job["config_version"],
                       "prompt_hash": hashlib.sha256((instructions + request_prompt).encode()).hexdigest(),
                       "recovery": recovery, "status": "started",
                       "started_at": time.time(), "invocation": invocation}
            if alias != settings[role][0]:
                attempt["fallback_for"] = settings[role][0]
            job["attempts"].append(attempt)
            # Save the attempt before contacting the provider so a crash still counts.
            checkpoint(job)
        retryable = True
        try:
            output = call_and_validate_stage(
                alias, request_prompt, reasoning, instructions, schema,
                output_tokens, record_type, validate, attempt, state_lock,
            )
        except Exception as error:
            message, kind, retryable = stage_error(error)
            with state_lock:
                attempt.update({"status": "failed", "error": message, "failure_kind": kind,
                                "error_type": type(error).__name__,
                                "http_status": getattr(error, "status_code", None) or getattr(error, "code", None)})
            # Respect Retry-After only when the wait is short.
            headers = getattr(getattr(error, "response", None), "headers", {}) or {}
            retry_after = headers.get("retry-after")
            try:
                delay = float(retry_after) if retry_after is not None else 1
            except (ValueError, TypeError):
                delay = 1
            if delay < 0 or delay > 30:
                retryable = False
            if fallback and recovery == 0:
                retryable = True
                delay = 0
            if retryable and recovery == 0:
                time.sleep(delay)
        else:
            with state_lock:
                attempt["status"] = "completed"
                job["stages"][name] = {"fingerprint": fingerprint, "output": output.model_dump()}
        finally:
            with state_lock:
                checkpoint(job)
        if attempt["status"] == "completed":
            return output
        if not retryable:
            break
    error_message = "No recovery attempts remain"
    for earlier in reversed(job["attempts"]):
        if earlier["name"] == name and earlier["specification_version"] == job["specification_version"]:
            error_message = earlier.get("error", error_message)
            break
    raise StageError(f"{name}: {error_message}.")


def set_phase(job, phase, checkpoint):
    job["phase"] = phase
    checkpoint(job)


def independent_plans(job, inputs, checkpoint):
    """Two independent estimates, with serialized queue checkpoints."""
    lock = RLock()
    estimates, errors = {}, {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        primary_future = executor.submit(
            run_stage, job, "primary_initial", "planner", Estimate, inputs,
            ai_config.PLANNER_PROMPT, checkpoint, check_estimate, lock,
        )
        secondary_future = executor.submit(
            run_stage, job, "secondary_initial", "second_planner", Estimate, inputs,
            ai_config.SECOND_PLANNER_PROMPT, checkpoint, check_estimate, lock,
        )
        try:
            estimates["primary"] = primary_future.result().model_dump()
        except Exception as error:
            errors["primary"] = error
        try:
            estimates["secondary"] = secondary_future.result().model_dump()
        except Exception as error:
            errors["secondary"] = error
    if errors:
        label = next(iter(errors))
        job["current_stage"] = label + "_initial"
        raise errors[label]
    return estimates


def ask_questions(job, questions, checkpoint):
    job["questions"] = [{"id": f"Q{index}", "question": question}
                        for index, question in enumerate(questions, 1)]
    job["status"] = "needs_input"
    job["phase"] = "Project details needed"
    checkpoint(job)


def finish_plan(job, estimate, estimates, checkpoint):
    """Save the reviewed result and pause if it needs more user details."""
    degraded = any(
        attempt.get("fallback_for") and attempt["status"] == "completed"
        and attempt["specification_version"] == job["specification_version"]
        for attempt in job["attempts"]
    )
    warnings = list(estimate.warnings)
    for material in estimate.materials:
        if material.calculation.method == "manual":
            warnings.append(f"{material.name}: manual estimate; quantity arithmetic is unverified.")
        if material.quantity is None:
            warnings.append(f"{material.name}: quantity is unknown.")
    if degraded:
        warnings.append("Review used the Gemini High fallback instead of Nemotron.")
    partial = degraded or bool(estimate.questions or estimate.warnings) or any(
        material.quantity is None for material in estimate.materials)
    job["result"] = {
        "format_version": 2, "tier": job["tier"],
        "planning_status": "partial" if partial else "complete",
        "estimate": estimate.model_dump(), "warnings": warnings,
        "independent_estimates": estimates, "review_process_degraded": degraded,
        "audited": True, "plan_version": job["plan_version"],
    }
    if estimate.questions:
        ask_questions(job, estimate.questions, checkpoint)
    else:
        job["questions"] = []
        job["status"] = job["result"]["planning_status"]
        job["phase"] = "Review needed" if partial else "Complete"
        checkpoint(job)
    return job


def run_workflow(job, checkpoint):
    if job["config_version"] != ai_config.WORKFLOW_VERSION:
        raise StageError("This job uses an older format. Start a new job; saved results remain available.")
    settings = ai_config.WORKFLOW_TIERS[job["tier"]]
    if not settings["enabled"]:
        raise StageError("This planning tier is disabled.")
    if job["tier"] == "pro":
        from .jobs import pro_access_allowed
        if not pro_access_allowed(job["owner"]):
            raise StageError("Pro access is not enabled for this account.")
        for role in ["interpreter", "planner", "second_planner", "auditor", "auditor_fallback"]:
            if settings[role][1] != "high":
                raise StageError("Every Pro role must explicitly request High reasoning.")

    set_phase(job, "Interpreting", checkpoint)
    specification = run_stage(
        job, "interpret", "interpreter", Specification,
        {"original_request": job["original_request"], "answers": job["answers"],
         "previous_specification": job.get("previous_specification")},
        ai_config.INTERPRETER_PROMPT, checkpoint,
    )
    job["specification"] = specification.model_dump()
    if specification.questions:
        ask_questions(job, specification.questions, checkpoint)
        return job

    inputs = {"original_request": job["original_request"], "answers": job["answers"],
              "details": specification.model_dump()}
    set_phase(job, "Planning", checkpoint)
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

    set_phase(job, "Reviewing", checkpoint)
    estimate = run_stage(job, "review", "auditor", Estimate, review_inputs,
                         review_prompt, checkpoint, check_estimate)
    return finish_plan(job, estimate, estimates, checkpoint)
