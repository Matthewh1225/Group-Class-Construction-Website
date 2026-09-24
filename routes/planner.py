import json
from pathlib import Path

from flask import Blueprint, current_app, make_response, render_template, request
from itsdangerous import BadData, URLSafeTimedSerializer

from ProjectTemplates.projectTemplates import PROJECT_TEMPLATES
from utils.aiTools import audit_project, plan_project
from utils.ratelimits import limiter

planner_bp = Blueprint("planner", __name__)
DRAFT_MAX_AGE = 1800  # 30 minutes to submit

#save and encrypt the project draft from 1st ai for 2nd
def draft_signer():
    return URLSafeTimedSerializer(current_app.secret_key, salt="planner-draft")


def show_questions(draft, token, popup_message=None):
    return render_template(
        "planner_questions.html", draft=draft, draft_token=token,
        answers=request.form.getlist("answers"), popup_message=popup_message,
    )


def show_planner(ai_response, popup_message, project_mode, project_size,
                 project_template, form_data):
    return render_template(
        "planner.html",
        ai_response=ai_response,
        popup_message=popup_message,
        project_mode=project_mode,
        project_size=project_size,
        project_template=project_template,
        project_templates=PROJECT_TEMPLATES,
        form_data=form_data,
    )


def format_plan(plan):
    lines = []
    for material in plan["materials"]:
        amount = f"{material['quantity']:g} {material['unit']}"

        description = material["name"]
        if material["product_type"]:
            description += f" ({material['product_type']})"
        if material["specification"]:
            description += f" - {material['specification']}"
        if material["notes"]:
            description += f" - {material['notes']}"
        lines.append(f"{amount} - {description}")

    if not lines:
        lines.append("No materials found for this request.")

    if plan.get("corrections"):
        lines.append("\nCorrections:")
        lines.extend(plan["corrections"])

    return "\n".join(lines)


def planner_limit_reached(_limit):
    message = "Too many requests. Please wait."
    token = request.form.get("draftToken", "")
    if token:
        try:
            project_draft = draft_signer().loads(token, max_age=DRAFT_MAX_AGE)
        except BadData:
            pass
        else:
            return make_response(show_questions(project_draft, token, message), 429)
    return make_response(
        show_planner(
            None,
            message,
            request.form.get("projectMode"),
            request.form.get("projectSize"),
            request.form.get("projectTemplate"),
            request.form,
        ),
        429,
    )


@planner_bp.route("/planner", methods=["GET", "POST"])
@limiter.limit("4 per minute; 30 per hour", methods=["POST"], on_breach=planner_limit_reached)
def planner():
    form = request.form
    project_mode = form.get("projectMode")
    project_size = form.get("projectSize")
    project_template = form.get("projectTemplate")
    form_data = form

    if request.method == "GET":
        return show_planner(None, None, project_mode, project_size,
                            project_template, form_data)

    project_draft = None
    project_token = form.get("draftToken", "")
    popup_message = None
    ai_response = None

    try:
        if form.get("plannerAction") == "audit":
            project_draft = draft_signer().loads(project_token, max_age=DRAFT_MAX_AGE)
            form_data = project_draft["form"]
            project_data = project_draft["project"]
            project_mode = project_data["project_mode"]
            project_size = project_data["project_size"]
            project_template = project_data["project_template"]
            answers = form.getlist("answers")
            questions = project_draft["plan"]["questions"]
            if (len(answers) != len(questions)
                    or any(not answer.strip() for answer in answers)):
                return show_questions(project_draft, project_token, "Answer each question, or enter 'Not sure'.")
            result = audit_project(project_draft, answers)
        else:
            if project_mode == "template":
                selected_template = PROJECT_TEMPLATES.get(project_template)
                if selected_template is None:
                    project_mode = None
                    project_template = None
                    raise ValueError("Choose a valid project template.")
                project_size = selected_template["size"]
                project_data = selected_template["handler"](form)
            elif project_mode == "custom":
                user_input = form.get("userInput", "").strip()
                if not user_input:
                    raise ValueError("Describe your project first.")
                project_data = {"project_type": "custom", "description": user_input}
            else:
                project_mode = None
                raise ValueError("Choose a template or custom project.")

            project_data.update(
                project_mode=project_mode,
                project_size=project_size,
                project_template=project_template,
            )
            if project_mode == "custom" and project_size in {"large", "mega"}:
                plan_type = "pro"
            elif project_mode == "custom":
                plan_type = "basic"
            else:
                plan_type = form.get("planType", "basic")
            current_app.logger.info("AI request: plan_type=%s", plan_type)
            result = plan_project(project_data, plan_type)

            if plan_type == "pro":
                project_draft = result
                project_draft["form"] = dict(form)
                project_token = draft_signer().dumps(project_draft)
                if project_draft["plan"]["questions"]:
                    return show_questions(project_draft, project_token)
                result = audit_project(project_draft, [])

        ai_response = format_plan(result["plan"])

    except BadData:
        popup_message = "This draft expired or is invalid. Please start again."
    except ValueError as error:
        popup_message = str(error)
    except Exception as error:
        status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
        current_app.logger.exception("AI planning failed")
        if status_code == 429:
            popup_message = "AI limit reached."
        else:
            popup_message = "AI unavailable. Please try again later."
    else:
        metadata = result.copy()
        del metadata["text"]
        metadata.update({
            "project_mode": project_mode,
            "project_size": project_size,
            "project_template": project_template,
        })

        metadata_file = Path(current_app.root_path) / "ai_metadata.txt"
        with open(metadata_file, "a", encoding="utf-8") as file:
            json.dump(metadata, file, indent=4, default=str)
            file.write("\n\n")

    if project_draft is not None and popup_message:
        return show_questions(project_draft, project_token, popup_message)

    return show_planner(ai_response, popup_message, project_mode, project_size,
                        project_template, form_data)
