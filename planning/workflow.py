import json
import logging

import httpx
from google.genai.errors import APIError as GeminiAPIError
from groq import APIError as GroqAPIError, APIConnectionError, APITimeoutError
from mysql.connector import Error as MySQLError
from openrouter.errors import NoResponseError, OpenRouterError
from pydantic import ValidationError

from services.products import get_planner_catalog
from services.crews import CREW_RATES, HOURS_PER_DAY, MAX_DAYS, MAX_WORKERS, check_crew

from . import ai_config
from .ai_planner import AI_MODELS, ask_model
from .jobs import pro_access_allowed
from .schemas import (AuditedEstimate, CatalogMatches, DraftEstimate, PlanningError,
                      Specification, merge_catalog_matches)

MAX_QUESTIONS = 3
logger = logging.getLogger(__name__)

PROVIDER_ERRORS = (GeminiAPIError, GroqAPIError, OpenRouterError, NoResponseError,
                   httpx.TransportError, httpx.HTTPStatusError, TimeoutError, ConnectionError)


# Gemini names the HTTP status "code"; Groq and OpenRouter name it "status_code".
def error_code(error):
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code
    code = getattr(error, "status_code", None) or getattr(error, "code", None)
    if isinstance(code, int):
        return code
    return None

#group Error handling functions
def describe_error(error):
    code = error_code(error)
    if code == 429:
        return "the provider's rate or quota limit was reached (HTTP 429). Wait before retrying; check the account quota if it continues"
    if code == 401:
        return "the provider rejected authentication (HTTP 401). Check the configured API key"
    if code == 402:
        return "the provider requires payment or more credits (HTTP 402). Check the provider account"
    if code == 403:
        return "the provider denied access (HTTP 403). Check account permissions and model access"
    if code == 404:
        return "the requested model or endpoint was not found (HTTP 404). Check the configured model name"
    if code == 413:
        return "the request was too large (HTTP 413). Reduce the project or catalog sent to this stage"
    if code in (400, 422):
        return f"the provider rejected the request or its settings (HTTP {code}). Check model support for the schema, reasoning, and token settings"
    if code in (408, 504) or isinstance(error, (httpx.TimeoutException, APITimeoutError, TimeoutError)):
        return "the AI request timed out. Try again later or use a smaller project"
    if code is not None and code >= 500:
        return f"the provider reported a server error (HTTP {code}). Try again later"
    if isinstance(error, (httpx.TransportError, APIConnectionError, ConnectionError, NoResponseError)):
        return "the connection to the provider failed or no response was received. Check the connection and try again"
    if code is not None:
        return f"the provider rejected the request (HTTP {code})"
    return "the AI request failed without a specific error code"


def run_stage(tier, role, record_type, inputs, instructions):
    settings = ai_config.WORKFLOW_TIERS[tier][role]
    schema = record_type.model_json_schema()
    stage_name = role.replace("_", " ")
    model = AI_MODELS[settings["model"]]
    failure_prefix = f"The {stage_name} step failed ({model['provider']}: {model['model']})"

    try:
        text = ask_model(settings["model"], json.dumps(inputs, ensure_ascii=False),settings["reasoning"], instructions, schema, settings["output_tokens"])
        output = record_type.model_validate_json(text).model_dump()
        if record_type in (DraftEstimate, AuditedEstimate):
            for material in output["materials"]:
                material["product_id"] = None
        if record_type is AuditedEstimate:
            crew = output["crew"]
            if crew is not None:
                # Zero-worker roles do not contribute to the crew or its cost.
                crew["members"] = [member for member in crew["members"] if member["workers"] > 0]
            if crew is not None and crew["members"]:
                crew["label"] = "AI-estimated crew"
                output["crew"] = check_crew(crew)
            else:
                output["crew"] = None
        elif record_type is CatalogMatches:
            output = merge_catalog_matches(inputs["estimate"], output,
                                           inputs["material_catalog"], inputs["machinery_catalog"])
        return output
    except ValidationError as error:
        if error.errors()[0]["type"] == "json_invalid":
            detail = "the answer was not valid JSON, even though the provider reported completion"
        else:
            detail = "the answer was valid JSON but had missing fields or invalid values for the required format"
        message = f"{failure_prefix}: {detail}."
        logger.warning("%s", message)
        raise PlanningError(message) from error
    except (ValueError, PlanningError) as error:
        message = f"{failure_prefix}: {str(error).rstrip('.')}."
        logger.warning("%s", message)
        raise PlanningError(message) from error
    except PROVIDER_ERRORS as error:
        message = f"{failure_prefix}: {describe_error(error)}."
        logger.warning("%s", message)
        raise PlanningError(message) from error


def run_workflow(job, save_progress):
    tier = job["tier"]
    if tier == "pro" and not pro_access_allowed(job["owner"]):
        raise PlanningError(f"{ai_config.WORKFLOW_TIERS['pro']['label']} access is not enabled for this account.")

    def update_stage(role, state):
        job["stages"][role] = state
        save_progress(job)

    context = {"project": job["project"], "answers": job["answers"], "details": []}
    if job["stages"]["interpreter"] == "done":
        specification = job["specification"]
    else:
        update_stage("interpreter", "processing")
        specification = run_stage(tier, "interpreter", Specification, context,
                                  ai_config.INTERPRETER_PROMPT)
        job["specification"] = specification
        update_stage("interpreter", "done")

    # Limit follow-up questions to one round.
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

    roles = ["planner"]
    if tier == "pro":
        roles.append("second_planner")
    estimates = []
    for role in roles:
        update_stage(role, "processing")
        estimate = run_stage(tier, role, DraftEstimate, planner_inputs,
                             ai_config.PLANNER_PROMPT)
        estimates.append(estimate)
        update_stage(role, "done")

    update_stage("auditor", "processing")
    auditor_inputs = dict(planner_inputs)
    auditor_inputs["estimates"] = estimates
    auditor_inputs["available_crew_roles"] = {role: info["name"] for role, info in CREW_RATES.items()}
    auditor_inputs["hours_per_day"] = HOURS_PER_DAY
    auditor_inputs["max_workers_per_role"] = MAX_WORKERS
    auditor_inputs["max_working_days"] = MAX_DAYS
    result = run_stage(tier, "auditor", AuditedEstimate, auditor_inputs,
                       ai_config.AUDITOR_PROMPT)

    update_stage("auditor", "done")

    update_stage("matcher", "processing")
    matcher_inputs = dict(planner_inputs)
    matcher_inputs["estimate"] = result
    try:
        matcher_inputs["material_catalog"] = get_planner_catalog(materials=result["materials"])
        matcher_inputs["machinery_catalog"] = get_planner_catalog(machinery=True)
    except MySQLError as error:
        raise PlanningError("The matcher step failed: the product and machinery catalogs could not be loaded.") from error
    result = run_stage(tier, "matcher", CatalogMatches, matcher_inputs,
                       ai_config.MATCHER_PROMPT)

    job["stages"]["matcher"] = "done"
    job["result"] = result
    job["status"] = "complete"
    save_progress(job)
    return job
