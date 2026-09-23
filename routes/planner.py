import os
import json
from time import monotonic
from flask import Blueprint, current_app, make_response, render_template, request
from google import genai

from utils.ratelimits import limiter

planner_bp = Blueprint("planner", __name__)
Strongai = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
weakai = genai.Client(api_key=os.environ["GEMINI_API_KEY2"])

SYSTEM_INSTRUCTIONS = """
You are the BuildBetter construction project planner.
Be concise.
Only answer questions related to construction or DIY projects.
Do not explain your reasoning.
Do not calculate product prices.
Give detailed raw materils list as well as quantitites 
"""
TEMPLATES={
    "doghouse"            : "low" ,
    "concrete_slabs"      : "medium",
    "patio_deck"          :"medium",
    "residential_building":"high",
    "commercial_building" :"high",
    "wearhouse"           :"high"}

THINKING_LEVELS = {
    "small": "low",
    "medium": "medium",
    "large": "high",
    "mega": "high",}

AI_ERROR_MESSAGES = {
    400: "Gemini rejected the request. Check the server log for details.",
    401: "Gemini authentication failed. Check the configured API key.",
    403: "The configured API key does not have access to this Gemini request.",
    404: "The requested Gemini model could not be found.",
    429: "Gemini's usage limit has been reached. Please try again later.",
    500: "Gemini reported an internal server error. Please try again shortly.",
    502: "Gemini is temporarily unavailable. Please try again shortly.",
    503: "Gemini is busy or unavailable. Please try again shortly.",
    504: "Gemini could not finish before its deadline. Try a smaller project or try again later.",
}
AI_MODELS={
    "weak":  "gemini-3.5-flash-lite",
    "strong":  "gemini-3.8-flash"
    }

@planner_bp.route("/planner", methods=["GET", "POST"])
@limiter.limit(
    "2 per minute; 20 per hour",
    methods=["POST"],
    #called when rate limit is hit
    on_breach=lambda _: make_response(
        render_template(
            "planner.html",
            ai_response=None,
            popup_message="You have planned too many projects. Please wait.",
            project_mode=request.form.get("projectMode"),
            project_size=request.form.get("projectSize"),
            project_template=request.form.get("projectTemplate"),
        ),
        429,
    ),
)
def planner():
    project_mode = request.form.get("projectMode")
    project_size = request.form.get("projectSize")
    project_template = request.form.get("projectTemplate")
    popup_message = None
    ai_response = None

    if request.method == "POST":
        user_input = request.form.get("userInput", "").strip()
        if project_mode == "template" and project_template == "deck":
            deck_data = {
                "project_type": "deck",
                "dimensions": {
                    "length_ft": request.form.get("lengthFt", type=float),
                    "width_ft": request.form.get("widthFt", type=float),
                    "height_ft": request.form.get("heightFt", type=float),
                },
                "decking": request.form.get("decking"),
                "railing": request.form.get("railing") == "yes",
                "stairs": request.form.get("stairs") == "yes",
                "description": user_input,
            }
            ai_input = json.dumps(deck_data, indent=2)
        else:
            ai_input = f"""
            Planning method: {project_mode}
            Selected template: {project_template or "None"}
            Project size: {project_size}
            Project description: {user_input}
            """

        thinking_level = THINKING_LEVELS.get(project_size, "low")
        started_at = monotonic()

        try:
            if thinking_level in {"low", "medium"}:
                ai = weakai
                model = AI_MODELS["weak"]#currednt model 3.5 flash light 
            else:
                ai = Strongai
                model = AI_MODELS["weak"]#can change to strong t use gemini 3.8 flash

            current_app.logger.info(
                "Gemini request: model=%s thinking_level=%s", model, thinking_level
            )
            response = ai.interactions.create(
                model=model,
                system_instruction=SYSTEM_INSTRUCTIONS,
                generation_config={"thinking_level": thinking_level},
                input=ai_input,
                timeout=120,
            )
            ai_response = response.output_text

        except Exception as error:
            status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
            current_app.logger.exception(
                "Gemini request failed: model=%s thinking_level=%s error=%s status=%s elapsed=%.1fs",
                model, thinking_level, type(error).__name__, status_code,
                monotonic() - started_at,
            )
            popup_message = AI_ERROR_MESSAGES.get(
                status_code,
                "The AI planner could not complete the request.Check the server log for details.",
            )
        else:
            if not ai_response:
                popup_message = "Gemini returned no plan. Try a smaller project or rephrase your request."
            # Usage is optional. A metadata problem must not discard a valid plan.
            usage = getattr(response, "usage", None)
            metadata = {
                "id": response.id,
                "model": response.model,
                "status": response.status,
                "project_mode": project_mode,
                "project_size": project_size,
                "project_template": project_template,
                "thinking_level": thinking_level,
                "elapsed_seconds": round(monotonic() - started_at, 2),
                "thinking_tokens": getattr(usage, "total_thought_tokens", None),
                "input_tokens": getattr(usage, "total_input_tokens", None),
                "output_tokens": getattr(usage, "total_output_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            }

            try:
                with open("ai_metadata.txt", "a", encoding="utf-8") as file:
                    json.dump(metadata, file, indent=4, default=str)
                    file.write("\n\n")
            except OSError:
                current_app.logger.exception("Could not save Gemini response metadata")

    return render_template(
        "planner.html",
        ai_response=ai_response,
        popup_message=popup_message,
        project_mode=project_mode,
        project_size=project_size,
        project_template=project_template,
    )
