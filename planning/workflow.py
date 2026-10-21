import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from google.genai.errors import APIError as GeminiAPIError
from groq import APIError as GroqAPIError, APIConnectionError, APIResponseValidationError
from openrouter.errors import OpenRouterError, NoResponseError, ResponseValidationError
from pydantic import ValidationError

from services.products import get_planner_catalog
from services.crews import CREW_RATES, HOURS_PER_DAY, MAX_DAYS, MAX_WORKERS, parse_crew

from . import ai_config
from .ai_planner import ask_model, check_model
from .jobs import pro_access_allowed
from .schemas import AuditedEstimate, BadAnswer, DraftEstimate, Specification, check_estimate

logger = logging.getLogger(__name__)

MAX_QUESTIONS = 3
RETRY_DELAY = 2  # seconds between tries
MAX_RETRY_DELAY = 30  # longest allowed wait

# Unexpected errors stop the job without another AI call.
STAGE_ERRORS = (GeminiAPIError, GroqAPIError, OpenRouterError, NoResponseError,
                httpx.TransportError, TimeoutError, ConnectionError, BadAnswer)


# The page shows this error to the user.
class PlanningError(Exception):
    pass


def describe_error(error):
    if isinstance(error, BadAnswer):
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


def can_retry(error):
    code = getattr(error, "status_code", None) or getattr(error, "code", None)
    if isinstance(code, int) and code >= 400:
        # Groq uses HTTP 400 for some bad AI answers; those can be retried.
        if code == 400 and isinstance(error, GroqAPIError) and isinstance(error.body, dict):
            details = error.body.get("error", error.body)
            if isinstance(details, dict) and details.get("code") == "json_validate_failed":
                return True
        return code in (408, 409, 429) or 500 <= code < 600
    return isinstance(error, (BadAnswer, APIResponseValidationError, ResponseValidationError,
                              APIConnectionError, NoResponseError, httpx.TimeoutException,
                              httpx.NetworkError, httpx.RemoteProtocolError,
                              TimeoutError, ConnectionError))


# None means the requested wait is too long.
def retry_delay(error):
    response = getattr(error, "response", None)
    if response is None:
        response = getattr(error, "raw_response", None)
    headers = getattr(response, "headers", {})
    try:
        delay = float(headers.get("retry-after"))
    except (TypeError, ValueError):
        # Use the usual delay if the header is missing or is not a number.
        return RETRY_DELAY
    if delay > MAX_RETRY_DELAY:
        return None
    return max(RETRY_DELAY, delay)


# Pro's auditor uses its fallback on retry or if its main model is not set up.
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


def run_stage(tier, role, record_type, inputs, instructions, catalog_ids):
    role_settings = ai_config.WORKFLOW_TIERS[tier][role]
    schema = record_type.model_json_schema()
    problem = None
    answer_problem = None  # only bad answers go back to the AI
    model_name = pick_model(role_settings, second_try=False)

    for try_number in (1, 2):
        request = dict(inputs)
        if answer_problem:
            request["problem_with_last_answer"] = answer_problem
        prompt = json.dumps(request, ensure_ascii=False, allow_nan=False)
        try:
            text = ask_model(model_name, prompt, role_settings["reasoning"], instructions,
                             schema, role_settings["output_tokens"])
            try:
                data = json.loads(text)
                crew_missing = (record_type is AuditedEstimate and isinstance(data, dict)
                                and data.get("crew") is None)
                if crew_missing:
                    data["crew"] = {
                        "days": [1, 2],
                        "members": [{"role": "general", "workers": 1, "days": [1, 2]}],
                    }
                output = record_type.model_validate(data).model_dump()
            except ValidationError as error:
                problems = []
                for problem in error.errors(include_url=False, include_input=False)[:8]:
                    field = ".".join(str(part) for part in problem["loc"])
                    problems.append(f"{field}: {problem['msg']}")
                raise BadAnswer("Fix these fields: " + "; ".join(problems) +
                                ". Every material needs a positive numeric quantity; "
                                "use labeled assumptions for missing dimensions.") from error
            except json.JSONDecodeError as error:
                raise BadAnswer("Return valid JSON matching the required format.") from error
            if issubclass(record_type, DraftEstimate):
                check_estimate(output, catalog_ids)
            if record_type is AuditedEstimate:
                output["crew"]["label"] = "AI-estimated crew"
                try:
                    output["crew"] = parse_crew(json.dumps(output["crew"]))
                except ValueError as error:
                    raise BadAnswer(str(error)) from error
                if crew_missing:
                    output["notes"].append(
                        "Crew details were not returned, so 1 general laborer for 1-2 working days "
                        "is a provisional starting allowance. Review the crew and completion days "
                        "for this project's scope; larger or specialized jobs will need more."
                    )
            return output
        except STAGE_ERRORS as error:
            problem = describe_error(error)
            logger.warning("%s try %s with %s failed: %s", role, try_number, model_name, problem)
            # Send feedback about bad answers, not network or account errors.
            if isinstance(error, BadAnswer):
                answer_problem = problem
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
            # A different provider does not need the same wait.
            model_name = next_model

    raise PlanningError(f"The {role.replace('_', ' ')} step failed: {problem}.")


# Pro runs both planners at once. One usable estimate is enough.
def run_two_planners(tier, inputs, catalog_ids):
    estimates = []
    problems = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(run_stage, tier, "planner", DraftEstimate, inputs,
                                ai_config.PLANNER_PROMPT, catalog_ids)
        second = executor.submit(run_stage, tier, "second_planner", DraftEstimate, inputs,
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


def run_workflow(job, save_progress):
    tier = job["tier"]
    if tier == "pro" and not pro_access_allowed(job["owner"]):
        raise PlanningError(f"{ai_config.WORKFLOW_TIERS['pro']['label']} access is not enabled for this account.")

    # The interpreter does not choose products.
    job["phase"] = "Interpreting"
    save_progress(job)
    context = {"project": job["project"], "answers": job["answers"], "details": []}
    specification = run_stage(tier, "interpreter", Specification,
                              context,
                              ai_config.INTERPRETER_PROMPT, set())
    job["specification"] = specification

    # Ask questions once, then estimate missing details using reasonable assumptions.
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

    catalog = get_planner_catalog()
    catalog_ids = set()
    for product in catalog:
        catalog_ids.add(product["product_id"])
    context["details"] = specification["details"]
    inputs = {**context, "catalog": catalog}
    review_inputs = dict(inputs)

    job["phase"] = "Planning"
    save_progress(job)
    if tier == "pro":
        review_inputs["estimates"] = run_two_planners(tier, inputs, catalog_ids)
    else:
        review_inputs["estimates"] = [run_stage(tier, "planner", DraftEstimate, inputs,
                                               ai_config.PLANNER_PROMPT, catalog_ids)]

    job["phase"] = "Reviewing"
    save_progress(job)
    review_inputs["available_crew_roles"] = {role: info["name"] for role, info in CREW_RATES.items()}
    review_inputs["hours_per_day"] = HOURS_PER_DAY
    review_inputs["max_workers_per_role"] = MAX_WORKERS
    review_inputs["max_working_days"] = MAX_DAYS
    result = run_stage(tier, "auditor", AuditedEstimate, review_inputs,
                       ai_config.AUDITOR_PROMPT, catalog_ids)

    result["planning_status"] = "complete"
    job["result"] = result
    job["status"] = "complete"
    job["phase"] = "Complete"
    save_progress(job)
    return job
