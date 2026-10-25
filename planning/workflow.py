import json

import httpx
from google.genai.errors import APIError as GeminiAPIError
from groq import APIError as GroqAPIError
from mysql.connector import Error as MySQLError
from openrouter.errors import NoResponseError, OpenRouterError
from pydantic import ValidationError

from services.products import get_planner_catalog
from services.crews import CREW_RATES, HOURS_PER_DAY, MAX_DAYS, MAX_WORKERS, check_crew

from . import ai_config
from .ai_planner import ask_model
from .jobs import pro_access_allowed
from .schemas import (AuditedEstimate, DraftEstimate, PlanningError, Specification,
                      clear_unknown_products)

MAX_QUESTIONS = 3

PROVIDER_ERRORS = (GeminiAPIError, GroqAPIError, OpenRouterError, NoResponseError,
                   httpx.TransportError, TimeoutError, ConnectionError)


# Gemini names the HTTP status "code"; Groq and OpenRouter name it "status_code".
def error_code(error):
    code = getattr(error, "status_code", None) or getattr(error, "code", None)
    if isinstance(code, int):
        return code
    return None

#group: Error handling functions
def describe_error(error):
    code = error_code(error)
    if code == 429:
        return "the AI provider's rate limit was reached"
    if code in (401, 402, 403, 404):
        return "the AI model or its account is unavailable"
    if code in (400, 413, 422):
        return "the AI provider rejected the request"
    return "the AI request failed or timed out"


def run_stage(tier, role, record_type, inputs, instructions):
    settings = ai_config.WORKFLOW_TIERS[tier][role]
    schema = record_type.model_json_schema()
    stage_name = role.replace("_", " ")

    try:
        text = ask_model(settings["model"], json.dumps(inputs, ensure_ascii=False),
                         settings["reasoning"], instructions, schema,
                         settings["output_tokens"])
        output = record_type.model_validate_json(text).model_dump()
        if record_type is AuditedEstimate:
            catalog_ids = {product["product_id"] for product in inputs.get("catalog", [])}
            clear_unknown_products(output, catalog_ids)
            output["crew"]["label"] = "AI-estimated crew"
            output["crew"] = check_crew(output["crew"])
        elif record_type is DraftEstimate:
            # Drafts describe materials; only the auditor assigns store IDs.
            for material in output["materials"]:
                material["product_id"] = None
        return output
    except ValidationError as error:
        raise PlanningError(f"The {stage_name} step failed: the AI answer was incomplete or invalid.") from error
    except (ValueError, PlanningError) as error:
        raise PlanningError(f"The {stage_name} step failed: {str(error).rstrip('.')}.") from error
    except PROVIDER_ERRORS as error:
        raise PlanningError(f"The {stage_name} step failed: {describe_error(error)}.") from error


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

    # Limit follow-up questions to one rtime.
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
    # matching products from the db
    try:
        auditor_inputs["catalog"] = get_planner_catalog()
    except MySQLError as error:
        raise PlanningError("The auditor step failed: the product catalog could not be loaded.") from error
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
