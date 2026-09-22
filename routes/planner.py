import os
import json
from dotenv import load_dotenv
from flask import Blueprint, render_template,request,current_app
from google import genai
from google.genai import types
from Ratelimits import limiter

load_dotenv()
planner_bp = Blueprint("planner", __name__)
ai=genai.Client()
#Outline for the ai, need to to be more precise in accordance with our db structure
system_instructions="""
    You are the BuildBetter construction project planner.
    Be concise.
    Only answer questions related to construction or DIY projects.
    Do not explain your reasoning.
    Do not calculate product prices."""

#gemini api GET/POST,needs to be structed to get precise input and output
@planner_bp.route("/planner",methods=["GET","POST"])
#limit ai messges
@limiter.limit(
    "2 per minute; 20 per hour",
    methods=["POST"],
    error_message="You have planned too many projects. Please wait.",
)
def planner():
    popup_message = None
    ai_response=None
    metadata = None
    if request.method == "POST":
        try:
            userInput = request.form.get("userInput")
            response = ai.interactions.create(
            #model="gemini-3.8-flash",
            model="gemini-3.5-flash-lite",
            system_instruction=system_instructions,
            #config=types.GenerateContentConfig(max_output_tokens=)
            generation_config={"thinking_level": "low"},
            input=userInput)
            ai_response=response.output_text

        except Exception as error:
            current_app.logger.exception("Gemini request failed")

            if getattr(error, "status_code", None) == 429:
                popup_message = "The daily Gemini request limit has been reached."
            else:
                popup_message = "The AI service is temporarily unavailable."

        if ai_response is not None:
            metadata = {
                "id": response.id,
                "model": response.model,
                "status": response.status,
                "thinking tokens": response.usage.total_thought_tokens,
                "input_tokens": response.usage.total_input_tokens,
                "output_tokens": response.usage.total_output_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            METADATA_FILE = "ai_metadata.txt"
            with open(METADATA_FILE, "a", encoding="utf-8") as file:
                json.dump(metadata, file, indent=4, default=str)
                file.write("\n\n")

    return render_template("planner.html",ai_response=ai_response,metadata=metadata,popup_message=popup_message)

