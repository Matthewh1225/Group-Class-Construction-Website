import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from google.genai.errors import APIError as GeminiAPIError
from groq import APIError as GroqAPIError
from openrouter.errors import NoResponseError, OpenRouterError
from pydantic import ValidationError

from services.products import get_planner_catalog
from services.crews import CREW_RATES, HOURS_PER_DAY, MAX_DAYS, MAX_WORKERS, check_crew

from . import ai_config
from .ai_planner import ask_model
from .jobs import pro_access_allowed
from .schemas import (AuditedEstimate, BadAnswer, DraftEstimate, PlanningError, Specification,
                      clear_unknown_products)

logger = logging.getLogger(__name__)

MAX_QUESTIONS = 3
RETRY_DELAY = 5  # seconds to wait after a provider error

# Provider and network errors. Any other error is a bug, so it is not retried.
PROVIDER_ERRORS = (GeminiAPIError, GroqAPIError, OpenRouterError, NoResponseError,
                   httpx.TransportError, TimeoutError, ConnectionError)

# Account, model and request errors fail the same way if the same model is asked again.
DO_NOT_RETRY = (400, 401, 402, 403, 404, 413, 422)


# Gemini names the HTTP status "code"; Groq and OpenRouter name it "status_code".
def error_code(error):
    code = getattr(error, "status_code", None) or getattr(error, "code", None)
    if isinstance(code, int):
        return code
    return None


# Users see these messages, never the provider's own error text.
def describe_error(error):
    code = error_code(error)
    if code == 429:
        return "the AI provider's rate limit was reached"
    if code in (401, 402, 403, 404):
        return "the AI model or its account is unavailable"
    if code in (400, 413, 422):
        return "the AI provider rejected the request"
    return "the AI request failed or timed out"


# The message sent back to the AI when its answer does not match the schema.
def validation_feedback(error, record_type):
    problems = []
    for item in error.errors(include_url=False, include_input=False)[:8]:
        location = []
        for part in item["loc"]:
            location.append(str(part))
        field = ".".join(location) or "answer"
        problems.append(f"{field}: {item['msg']}")
    feedback = "Fix these fields: " + "; ".join(problems) + "."
    if record_type is not Specification:
        feedback += (" Every material needs a positive numeric quantity; "
                     "use labeled assumptions for missing dimensions.")
    return feedback


# Each stage gets at most two tries. A bad answer is sent back so the AI can fix it.
def run_stage(tier, role, record_type, inputs, instructions):
    settings = ai_config.WORKFLOW_TIERS[tier][role]
    schema = record_type.model_json_schema()
    request = dict(inputs)
    has_fallback = "fallback" in settings
    problem = None

    for attempt in (1, 2):
        # Pro's auditor uses its fallback model for the second try.
        model_name = settings["model"]
        if attempt == 2 and has_fallback:
            model_name = settings["fallback"]

        try:
            text = ask_model(model_name, json.dumps(request, ensure_ascii=False),
                             settings["reasoning"], instructions, schema,
                             settings["output_tokens"])
            output = record_type.model_validate_json(text).model_dump()
            if record_type is AuditedEstimate:
                catalog_ids = {product["product_id"] for product in inputs.get("catalog", [])}
                clear_unknown_products(output, catalog_ids)
                output["crew"]["label"] = "AI-estimated crew"
                try:
                    output["crew"] = check_crew(output["crew"])
                except ValueError as error:
                    raise BadAnswer(str(error)) from error
            elif record_type is DraftEstimate:
                # Drafts describe materials; only the auditor assigns store IDs.
                for material in output["materials"]:
                    material["product_id"] = None
            return output
        # Each branch below decides two things:
        #   try_again  - is a second try worth making?
        #   wait_first - should we pause before it?
        except ValidationError as error:
            problem = validation_feedback(error, record_type)
            request["problem_with_last_answer"] = problem
            try_again = True
            wait_first = False
        except BadAnswer as error:
            problem = str(error)
            request["problem_with_last_answer"] = problem
            try_again = True
            wait_first = False
        except PlanningError as error:
            # The model has no API key, so only a different (fallback) model can help.
            problem = str(error)
            try_again = has_fallback
            wait_first = False
        except PROVIDER_ERRORS as error:
            # Network and account problems are not the AI's fault, so no feedback is sent.
            # Account and request errors (such as a bad key) fail the same way every time,
            # so waiting does not help: switch to the fallback model straight away.
            problem = describe_error(error)
            might_clear_up = error_code(error) not in DO_NOT_RETRY
            try_again = has_fallback or might_clear_up
            wait_first = might_clear_up

        logger.warning("%s attempt %s with %s failed: %s", role, attempt, model_name, problem)
        # Stop after the second try, or when another try cannot help.
        if attempt == 2 or not try_again:
            break
        if wait_first:
            time.sleep(RETRY_DELAY)

    raise PlanningError(f"The {role.replace('_', ' ')} step failed: {problem.rstrip('.')}.")


# Pro runs both planners at the same time. One usable estimate is enough.
def run_two_planners(tier, inputs, update_stage):
    estimates = []
    problems = []
    bug = None
    with ThreadPoolExecutor(max_workers=2) as executor:
        update_stage("planner", "processing")
        update_stage("second_planner", "processing")
        first = executor.submit(run_stage, tier, "planner", DraftEstimate, inputs,
                                ai_config.PLANNER_PROMPT)
        second = executor.submit(run_stage, tier, "second_planner", DraftEstimate, inputs,
                                 ai_config.PLANNER_PROMPT)
        for role, planner in (("planner", first), ("second_planner", second)):
            try:
                estimate = planner.result()
            except PlanningError as error:
                problems.append(str(error))
                update_stage(role, "failed")
            except Exception as error:
                # Show both planners' real outcomes before the bug stops the job.
                bug = error
                update_stage(role, "failed")
            else:
                estimates.append(estimate)
                update_stage(role, "done")
    if bug is not None:
        raise bug
    if not estimates:
        raise PlanningError("Both planners failed. " + " ".join(problems))
    if problems:
        logger.warning("One Pro planner failed; reviewing the other estimate. %s", problems[0])
    return estimates


# The job's stages were set to pending when it was queued.
def run_workflow(job, save_progress):
    tier = job["tier"]
    if tier == "pro" and not pro_access_allowed(job["owner"]):
        raise PlanningError(f"{ai_config.WORKFLOW_TIERS['pro']['label']} access is not enabled for this account.")

    def update_stage(role, state):
        job["stages"][role] = state
        save_progress(job)

    # The interpreter does not choose products.
    update_stage("interpreter", "processing")
    context = {"project": job["project"], "answers": job["answers"], "details": []}
    specification = run_stage(tier, "interpreter", Specification, context,
                              ai_config.INTERPRETER_PROMPT)
    job["specification"] = specification
    update_stage("interpreter", "done")

    # Ask questions once, then estimate missing details using reasonable assumptions.
    # The schema has already trimmed the questions.
    questions = []
    for question in specification["questions"]:
        if question:
            questions.append(question)
    if questions and not job["answers"]:
        job["questions"] = questions[:MAX_QUESTIONS]
        job["status"] = "needs_input"
        save_progress(job)
        return job

    planner_inputs = dict(context)
    planner_inputs["details"] = specification["details"]

    if tier == "pro":
        estimates = run_two_planners(tier, planner_inputs, update_stage)
    else:
        update_stage("planner", "processing")
        estimates = [run_stage(tier, "planner", DraftEstimate, planner_inputs,
                               ai_config.PLANNER_PROMPT)]
        update_stage("planner", "done")

    update_stage("auditor", "processing")
    auditor_inputs = dict(planner_inputs)
    # Store matching happens only after the planners have estimated the whole project.
    auditor_inputs["catalog"] = get_planner_catalog()
    auditor_inputs["estimates"] = estimates
    auditor_inputs["available_crew_roles"] = {role: info["name"] for role, info in CREW_RATES.items()}
    auditor_inputs["hours_per_day"] = HOURS_PER_DAY
    auditor_inputs["max_workers_per_role"] = MAX_WORKERS
    auditor_inputs["max_working_days"] = MAX_DAYS
    result = run_stage(tier, "auditor", AuditedEstimate, auditor_inputs,
                       ai_config.AUDITOR_PROMPT)

    job["stages"]["auditor"] = "done"
    job["result"] = result
    job["status"] = "complete"
    save_progress(job)
    return job
