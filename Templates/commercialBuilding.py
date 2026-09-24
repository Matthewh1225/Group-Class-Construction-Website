def build_commercial_building(form):
    return {
        "project_type": "commercial_building",
        "floors": form.get("floors", type=int),
        "rooms": form.get("rooms", type=int),
        "elevator": form.get("elevator") == "yes",
        "description": form.get("userInput", "").strip(),
    }
