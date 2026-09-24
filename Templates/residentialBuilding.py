def build_residential_building(form):
    return {
        "project_type": "residential_building",
        "floors": form.get("floors", type=int),
        "bedrooms": form.get("bedrooms", type=int),
        "bathrooms": form.get("bathrooms", type=int),
        "description": form.get("userInput", "").strip(),
    }
