
import json   
from flask import  request

def deckTemplate():
    user_input = request.form.get("userInput", "").strip()
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
    return ai_input