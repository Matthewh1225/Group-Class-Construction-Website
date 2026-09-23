import json

from flask import Blueprint, current_app, make_response, render_template, request
from google import genai

from utils.ratelimits import limiter

planner_bp = Blueprint("planner", __name__)
import os
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

THINKING_LEVELS = {
    "small": "low",
    "medium": "medium",
    "large": "high",
    "mega": "high",}

AI_ERROR_MESSAGES = {
    429: " AI usage limit has been hit. try again later.",
    503: "AI unavailable",}
AI_MODELS={
    "weak":  "gemini-3.5-flash-lite",
    "strong":  "gemini-3.8-flash"
    }

@planner_bp.route("/planner", methods=["GET", "POST"])
@limiter.limit(
    "2 per minute; 20 per hour",
    methods=["POST"],
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

        try:
            if thinking_level in {"low", "medium"}:
                ai = weakai
                model = AI_MODELS["weak"]
            else:
                ai = Strongai
                model = AI_MODELS["strong"]

            response = ai.interactions.create(
                model=model,
                system_instruction=SYSTEM_INSTRUCTIONS,
                generation_config={"thinking_level": thinking_level},
                input=ai_input,
                timeout=20,
            )

        except Exception as error:
            current_app.logger.exception("Gemini request failed")
            status_code = getattr(error, "status_code", None)
            popup_message = AI_ERROR_MESSAGES.get(status_code,"The AI planner is dead, try again.", )
        else:
            ai_response = response.output_text
            metadata = {
                "id": response.id,
                "model": response.model,
                "status": response.status,
                "project_mode": project_mode,
                "project_size": project_size,
                "project_template": project_template,
                "thinking_level": thinking_level,
                "thinking_tokens": response.usage.total_thought_tokens,
                "input_tokens": response.usage.total_input_tokens,
                "output_tokens": response.usage.total_output_tokens,
                "total_tokens": response.usage.total_tokens,
            }

            with open("ai_metadata.txt", "a", encoding="utf-8") as file:
                json.dump(metadata, file, indent=4, default=str)
                file.write("\n\n")

    return render_template(
        "planner.html",
        ai_response=ai_response,
        popup_message=popup_message,
        project_mode=project_mode,
        project_size=project_size,
        project_template=project_template,
    )
