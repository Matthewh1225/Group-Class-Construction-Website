import json
import logging

import httpx
from google.genai.errors import APIError as GeminiAPIError
from groq import APIError as GroqAPIError, APIConnectionError, APITimeoutError
from mysql.connector import Error as MySQLError
from pydantic import ValidationError

from services.products import get_catalog_classifications, get_material_candidates, get_machinery_catalog
from services.crews import CREW_RATES, HOURS_PER_DAY, MAX_DAYS, MAX_WORKERS, check_crew

from . import ai_config
from .ai_planner import AI_MODELS, ask_model
from .jobs import pro_access_allowed
from .schemas import (AnswerFormatError, AuditedEstimate, CatalogMatches, DraftEstimate,
                      PlanningError, Specification, merge_catalog_matches)

MAX_QUESTIONS = 3
# Retry a malformed answer once; provider errors go straight to the next fallback.
MAX_STAGE_ATTEMPTS = 2
ANSWER_ERRORS = (ValidationError, json.JSONDecodeError, AnswerFormatError)
logger = logging.getLogger(__name__)

PROVIDER_ERRORS = (GeminiAPIError, GroqAPIError,
                   httpx.TransportError, httpx.HTTPStatusError, TimeoutError, ConnectionError)


# Gemini uses code; Groq uses status_code.
def error_code(error):
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code
    code = getattr(error, "status_code", None) or getattr(error, "code", None)
    if isinstance(code, int):
        return code
    return None


def describe_error(error):
    code = error_code(error)
    if code == 429:
        return "AI service limit reached (HTTP 429). Try again later"
    if code == 401:
        return "AI service authentication failed (HTTP 401)"
    if code == 402:
        return "AI service credits unavailable (HTTP 402)"
    if code == 403:
        return "AI service access denied (HTTP 403)"
    if code == 404:
        return "AI model unavailable (HTTP 404)"
    if code == 413:
        return "Request too large (HTTP 413)"
    if code in (400, 422):
        return f"AI service rejected the request (HTTP {code})"
    if code in (408, 504) or isinstance(error, (httpx.TimeoutException, APITimeoutError, TimeoutError)):
        return "AI request timed out. Try again"
    if code is not None and code >= 500:
        return f"AI service unavailable (HTTP {code}). Try again later"
    if isinstance(error, (httpx.TransportError, APIConnectionError, ConnectionError)):
        return "Could not reach the AI service. Try again"
    if code is not None:
        return f"the provider rejected the request (HTTP {code})"
    return "AI request failed"


def clean_categories(output, classifications):
    for material in output["materials"]:
        category = material["category"]
        subcategory = material["subcategory"]
        if category not in classifications:
            material["category"] = None
            material["subcategory"] = None
        elif subcategory not in classifications[category]:
            material["subcategory"] = None


def clean_crew(crew):
    """Return a checked crew or None, keeping the materials if the crew is invalid."""
    if crew is None:
        return None
    if not isinstance(crew, dict) or not isinstance(crew.get("members"), list):
        logger.warning("The auditor's crew had an invalid format; keeping the estimate without a crew.")
        return None

    # Roles with zero workers aren't needed, so drop them instead of rejecting the crew.
    members = []
    for member in crew["members"]:
        if isinstance(member, dict) and member.get("workers") == 0:
            continue
        members.append(member)
    if not members:
        return None

    try:
        return check_crew({"label": "Suggested crew", "days": crew.get("days"), "members": members})
    except ValueError as error:
        logger.warning("The auditor's crew was invalid (%s); keeping the estimate without a crew.", error)
        return None


def parse_stage_answer(record_type, text, inputs):
    """Validate stage output, raising ANSWER_ERRORS for answers worth retrying."""
    data = json.loads(text)

    if record_type is CatalogMatches:
        return merge_catalog_matches(inputs["estimate"], data, inputs["material_candidates"],
                                     inputs["machinery_catalog"])

    # The crew is optional, so take it out and check it on its own after the materials.
    raw_crew = None
    if record_type is AuditedEstimate and isinstance(data, dict):
        raw_crew = data.get("crew")
        data["crew"] = None

    output = record_type.model_validate(data).model_dump()
    if record_type in (DraftEstimate, AuditedEstimate):
        for material in output["materials"]:
            material["product_id"] = None
    if record_type is AuditedEstimate:
        clean_categories(output, inputs["classifications"])
        output["crew"] = clean_crew(raw_crew)
    return output


def describe_answer_problem(error):
    if isinstance(error, ValidationError):
        problems = []
        for problem in error.errors()[:3]:
            location = ".".join(str(part) for part in problem["loc"]) or "answer"
            problems.append(f"{location}: {problem['msg']}")
        return "; ".join(problems)
    if isinstance(error, json.JSONDecodeError):
        return "the answer was not valid JSON"
    return str(error)


def answer_failure_detail(error):
    """The message shown to the user when every attempt gave a malformed answer."""
    if isinstance(error, json.JSONDecodeError):
        return "Invalid response format"
    if isinstance(error, ValidationError):
        if error.errors()[0]["type"] == "json_invalid":
            return "Invalid response format"
        return "Incomplete response"
    return str(error).rstrip(".")


class StageModelFailed(Exception):
    """A model failed a stage, with a short reason."""


def run_stage_with_model(stage_name, model_settings, record_type, inputs, instructions, renew_lease):
    """Ask one model for a stage's answer, asking once more if the answer is malformed."""
    schema = record_type.model_json_schema()
    model = AI_MODELS[model_settings["model"]]
    # No spaces after , and : keeps large requests (like the matcher's) smaller.
    inputs_text = json.dumps(inputs, ensure_ascii=False, separators=(",", ":"))
    prompt = inputs_text

    for attempt in range(1, MAX_STAGE_ATTEMPTS + 1):
        try:
            # Renew before every AI call, so no single wait can outlast the job's lease.
            renew_lease()
            text = ask_model(model_settings["model"], prompt, model_settings["reasoning"], instructions,
                             schema, model_settings["output_tokens"])
            return parse_stage_answer(record_type, text, inputs)
        except ANSWER_ERRORS as error:
            if attempt < MAX_STAGE_ATTEMPTS:
                feedback = describe_answer_problem(error)
                logger.warning("%s gave an invalid answer (%s); asking once more. (provider=%s model=%s)",
                               stage_name.capitalize(), feedback, model["provider"], model["model"])
                prompt = (inputs_text
                          + "\n\nYour previous answer was rejected: " + feedback
                          + ". Return the complete corrected JSON.")
                continue
            raise StageModelFailed(answer_failure_detail(error)) from error
        # Not retried: setup problems, token limits, blocked answers and other errors.
        except (ValueError, PlanningError) as error:
            raise StageModelFailed(str(error).rstrip(".")) from error
        except PROVIDER_ERRORS as error:
            raise StageModelFailed(describe_error(error)) from error


def run_stage(tier, role, record_type, inputs, instructions, renew_lease):
    """Run a stage, trying each fallback model in order if the one before it fails.

    renew_lease() saves progress and extends the lease; it raises LeaseLost if the job was cancelled or taken.
    """
    settings = ai_config.WORKFLOW_TIERS[tier][role]
    stage_name = role.replace("_", " ")
    problems = []

    for model_settings in [settings] + settings["fallbacks"]:
        model = AI_MODELS[model_settings["model"]]
        try:
            return run_stage_with_model(stage_name, model_settings, record_type, inputs, instructions, renew_lease)
        except StageModelFailed as error:
            problems.append(str(error))
            logger.warning("%s failed on %s: %s. (provider=%s)",
                           stage_name.capitalize(), model["model"], error, model["provider"])

    backups = "; ".join(problems[1:])
    message = (f"{stage_name.capitalize()} failed: {problems[0]}. "
               f"The backup {'model' if len(problems) == 2 else 'models'} also failed: {backups}.")
    raise PlanningError(message)


def run_workflow(job, save_progress):
    tier = job["tier"]
    if tier == "pro" and not pro_access_allowed(job["owner"]):
        raise PlanningError(f"{ai_config.WORKFLOW_TIERS['pro']['label']} access is not enabled for this account.")

    def update_stage(role, state):
        job["stages"][role] = state
        save_progress(job)

    def renew_lease():
        # Saving progress also extends the lease (jobs.save_job).
        save_progress(job)

    interpreter_inputs = {"project": job["project"], "answers": job["answers"]}
    if job["stages"]["interpreter"] == "done":
        specification = job["specification"]
    else:
        update_stage("interpreter", "processing")
        specification = run_stage(tier, "interpreter", Specification, interpreter_inputs,
                                  ai_config.INTERPRETER_PROMPT, renew_lease)
        job["specification"] = specification
        update_stage("interpreter", "done")

    # Ask questions once; later stages use the answers to replace earlier assumptions.
    questions = []
    for question in specification["questions"]:
        if question:
            questions.append(question)
    if questions and not job["answers"]:
        job["questions"] = questions[:MAX_QUESTIONS]
        job["status"] = "needs_input"
        save_progress(job)
        return job

    planner_inputs = dict(interpreter_inputs)
    planner_inputs["details"] = specification["details"]

    roles = ["planner"]
    if tier == "pro":
        roles.append("second_planner")
    # Save finished steps for restarts.
    saved = job.setdefault("checkpoints", {})

    estimates = []
    for role in roles:
        if role in saved:
            estimates.append(saved[role])
            continue
        update_stage(role, "processing")
        estimate = run_stage(tier, role, DraftEstimate, planner_inputs,
                             ai_config.PLANNER_PROMPT, renew_lease)
        saved[role] = estimate
        estimates.append(estimate)
        update_stage(role, "done")

    if "auditor" in saved:
        audited_estimate = saved["auditor"]
    else:
        update_stage("auditor", "processing")
        auditor_inputs = dict(planner_inputs)
        auditor_inputs["classifications"] = get_catalog_classifications()
        auditor_inputs["estimates"] = estimates
        auditor_inputs["available_crew_roles"] = {role: info["name"] for role, info in CREW_RATES.items()}
        auditor_inputs["hours_per_day"] = HOURS_PER_DAY
        auditor_inputs["max_workers_per_role"] = MAX_WORKERS
        auditor_inputs["max_working_days"] = MAX_DAYS
        audited_estimate = run_stage(tier, "auditor", AuditedEstimate, auditor_inputs,
                           ai_config.AUDITOR_PROMPT, renew_lease)
        saved["auditor"] = audited_estimate
        update_stage("auditor", "done")

    update_stage("matcher", "processing")
    matcher_inputs = dict(planner_inputs)
    matcher_inputs["estimate"] = audited_estimate
    try:
        matcher_inputs["material_candidates"] = get_material_candidates(audited_estimate["materials"])
        matcher_inputs["machinery_catalog"] = get_machinery_catalog()
    except MySQLError as error:
        raise PlanningError("The matcher step failed: the product and machinery catalogs could not be loaded.") from error
    matched_plan = run_stage(tier, "matcher", CatalogMatches, matcher_inputs, ai_config.MATCHER_PROMPT, renew_lease)

    job["stages"]["matcher"] = "done"
    job["result"] = matched_plan
    job["status"] = "complete"
    save_progress(job)
    return job
