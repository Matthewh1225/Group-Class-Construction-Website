import json
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime

import httpx
from google.genai.errors import APIError as GeminiAPIError
from groq import APIError as GroqAPIError, APIConnectionError, APIResponseValidationError
from openrouter.errors import OpenRouterError, NoResponseError, ResponseValidationError
from pydantic import ValidationError

from services.products import get_planner_catalog

from . import ai_config
from .ai_planner import ask_model, check_model
from .jobs import pro_access_allowed
from .schemas import BadAnswer, Estimate, Specification, check_estimate

logger = logging.getLogger(__name__)

MAX_QUESTIONS = 3
RETRY_DELAY = 2  # seconds to wait before the second try of a stage
MAX_RETRY_DELAY = 30  # longer provider cooldowns fail instead of holding the worker

# Expected stage failures. can_retry decides whether repeating the same model can help.
# Other exceptions are programming errors and reach the worker without another AI call.
STAGE_ERRORS = (GeminiAPIError, GroqAPIError, OpenRouterError, NoResponseError,
                httpx.TransportError, TimeoutError, ConnectionError, BadAnswer)


# Raised when a planning step cannot finish. Its message is shown to the user.
class PlanningError(Exception):
    pass


# Turns an error from one try into a short message that is safe to show the user.
def describe_error(error):
    if isinstance(error, BadAnswer):
        # our own checks explain the problem themselves
        return str(error)
    code = getattr(error, "status_code", None) or getattr(error, "code", None)
    if code == 429:
        return "the AI provider's rate limit was reached"
    if code in (401, 403, 404):
        return "the AI model is unavailable"
    if code in (400, 413, 422):
        return "the AI provider rejected the request"
    if code == 402:
        return "the AI provider's usage allowance is unavailable"
    if isinstance(code, int) and code >= 500:
        return "the AI provider is having problems"
    return "the AI request failed or timed out"


# Only temporary provider failures or invalid answers warrant repeating the same request.
def can_retry(error):
    code = getattr(error, "status_code", None) or getattr(error, "code", None)
    if isinstance(code, int) and code >= 400:
        # Groq can report a generated JSON validation failure as HTTP 400.
        # Other 400 errors (invalid schema, model or settings) will not improve on retry.
        if code == 400 and isinstance(error, GroqAPIError) and isinstance(error.body, dict):
            details = error.body.get("error", error.body)
            if isinstance(details, dict) and details.get("code") == "json_validate_failed":
                return True
        return code in (408, 409, 429) or 500 <= code < 600
    return isinstance(error, (BadAnswer, APIResponseValidationError, ResponseValidationError,
                              APIConnectionError, NoResponseError, httpx.TimeoutException,
                              httpx.NetworkError, httpx.RemoteProtocolError,
                              TimeoutError, ConnectionError))


# Respect Retry-After seconds or an HTTP date. None means the wait exceeds our limit.
def retry_delay(error):
    response = getattr(error, "response", None)
    if response is None:
        response = getattr(error, "raw_response", None)
    headers = getattr(response, "headers", {})
    value = headers.get("retry-after")
    if value is None:
        return RETRY_DELAY
    try:
        delay = float(value)
    except ValueError:
        try:
            delay = parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            return RETRY_DELAY
    if not math.isfinite(delay):
        return RETRY_DELAY
    if delay > MAX_RETRY_DELAY:
        return None
    return max(RETRY_DELAY, delay)


# Picks the model for one try of a role and checks it can be used (check_model).
# Only Pro's auditor has a fallback model: it is used for the second try, or straight away
# when the role's own model is not set up.
def pick_model(role_settings, second_try):
    choices = [role_settings["model"]]
    if "fallback" in role_settings:
        if second_try:
            choices.insert(0, role_settings["fallback"])
        else:
            choices.append(role_settings["fallback"])
    problem = "No model is configured."
    for model_name in choices:
        try:
            check_model(model_name, role_settings["reasoning"], role_settings["output_tokens"])
            return model_name
        except ValueError as error:
            problem = str(error)
    raise PlanningError(problem)


# Asks one AI model to do one stage and returns its checked answer as a plain dict.
# record_type is Specification (interpreter) or Estimate (planners and auditor).
# catalog_ids is the set of product IDs an estimate may use (the interpreter gets an empty set).
# A recoverable failure gets one more try; a configured fallback may also replace a
# permanently failing model. Raises PlanningError when no usable answer is obtained.
def run_stage(tier, role, record_type, inputs, instructions, catalog_ids):
    role_settings = ai_config.WORKFLOW_TIERS[tier][role]
    schema = record_type.model_json_schema()
    problem = None
    model_name = pick_model(role_settings, second_try=False)

    for try_number in (1, 2):
        request = dict(inputs)
        if problem:
            request["problem_with_last_answer"] = problem
        prompt = json.dumps(request, ensure_ascii=False, allow_nan=False)
        try:
            text = ask_model(model_name, prompt, role_settings["reasoning"], instructions,
                             schema, role_settings["output_tokens"])
            # The AI's JSON enters the application here, so this is where it is checked.
            try:
                output = record_type.model_validate_json(text).model_dump()
            except ValidationError as error:
                # SDK request-validation errors must not be mistaken for invalid AI output.
                raise BadAnswer("the AI answer did not match the required format") from error
            if record_type is Estimate:
                check_estimate(output, catalog_ids)
            return output
        except STAGE_ERRORS as error:
            problem = describe_error(error)
            logger.warning("%s try %s with %s failed: %s", role, try_number, model_name, problem)
            if try_number == 2:
                break
            next_model = pick_model(role_settings, second_try=True)
            if next_model == model_name:
                if not can_retry(error):
                    break
                delay = retry_delay(error)
                if delay is None:
                    break
                time.sleep(delay)
            # A different provider need not wait for the failed provider's cooldown.
            model_name = next_model

    raise PlanningError(f"The {role.replace('_', ' ')} step failed: {problem}.")


# Pro only: two planners write estimates at the same time, in two threads.
# Returns the estimates that worked (one or two). Raises PlanningError only if both planners failed.
# Any other error is a bug and is not caught here.
def run_two_planners(tier, inputs, catalog_ids):
    estimates = []
    problems = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(run_stage, tier, "planner", Estimate, inputs,
                                ai_config.PLANNER_PROMPT, catalog_ids)
        second = executor.submit(run_stage, tier, "second_planner", Estimate, inputs,
                                 ai_config.PLANNER_PROMPT, catalog_ids)
        for planner in [first, second]:
            try:
                estimates.append(planner.result())
            except PlanningError as error:
                problems.append(str(error))
    if not estimates:
        raise PlanningError("Both planners failed. " + " ".join(problems))
    if problems:
        logger.warning("One Pro planner failed; reviewing the other estimate. %s", problems[0])
    return estimates


# Runs the whole planning job from the start: interpret the request, maybe ask questions
# (one round only), plan, then review. save_progress(job) saves the job after each step.
def run_workflow(job, save_progress):
    tier = job["tier"]
    if tier == "pro" and not pro_access_allowed(job["owner"]):
        raise PlanningError(f"{ai_config.WORKFLOW_TIERS['pro']['label']} access is not enabled for this account.")

    # Step 1: the interpreter summarizes the request and may list missing details.
    # It picks no products, so it gets an empty set of catalog IDs.
    job["phase"] = "Interpreting"
    save_progress(job)
    specification = run_stage(tier, "interpreter", Specification,
                              {"original_request": job["project"], "answers": job["answers"]},
                              ai_config.INTERPRETER_PROMPT, set())
    job["specification"] = specification

    # Questions are only asked if the user has not answered any yet, so there is one round at most.
    # After that, missing details become unknown (None) quantities with a note.
    questions = []
    for question in specification["questions"]:
        if question.strip():
            questions.append(question.strip())
    if questions and not job["answers"]:
        job["questions"] = questions[:MAX_QUESTIONS]
        job["status"] = "needs_input"
        job["phase"] = "Project details needed"
        save_progress(job)
        return job

    # Step 2: write the estimate. The planners may only pick product IDs from this catalog.
    catalog = get_planner_catalog()
    catalog_ids = set()
    for product in catalog:
        catalog_ids.add(product["product_id"])
    # The planners get the interpreter's summary and details, but not its questions:
    # the question round is over, and the user's answers are in "answers".
    interpretation = {"summary": specification["summary"], "details": specification["details"]}
    inputs = {"original_request": job["project"], "answers": job["answers"],
              "interpretation": interpretation, "catalog": catalog}
    review_inputs = dict(inputs)

    job["phase"] = "Planning"
    save_progress(job)
    if tier == "pro":
        review_inputs["estimates"] = run_two_planners(tier, inputs, catalog_ids)
        review_prompt = ai_config.RECONCILER_PROMPT
    else:
        review_inputs["estimate"] = run_stage(tier, "planner", Estimate, inputs,
                                              ai_config.PLANNER_PROMPT, catalog_ids)
        review_prompt = ai_config.AUDITOR_PROMPT

    # Step 3: the auditor checks the draft (or reconciles Pro's estimates) and returns the final estimate.
    job["phase"] = "Reviewing"
    save_progress(job)
    result = run_stage(tier, "auditor", Estimate, review_inputs, review_prompt, catalog_ids)

    # The plan is "partial" when any material quantity is unknown.
    planning_status = "complete"
    for material in result["materials"]:
        if material["quantity"] is None:
            planning_status = "partial"
    result["planning_status"] = planning_status

    job["result"] = result
    job["status"] = planning_status
    if planning_status == "partial":
        job["phase"] = "Review needed"
    else:
        job["phase"] = "Complete"
    save_progress(job)
    return job
