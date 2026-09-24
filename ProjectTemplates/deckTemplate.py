def build_deck(form):
    return {
        "project_type": "deck",
        "dimensions": {
            "length_ft": form.get("lengthFt", type=float),
            "width_ft": form.get("widthFt", type=float),
            "height_ft": form.get("heightFt", type=float),
        },
        "decking": form.get("decking"),
        "railing": form.get("railing") == "yes",
        "stairs": form.get("stairs") == "yes",
        "description": form.get("userInput", "").strip(),
    }
