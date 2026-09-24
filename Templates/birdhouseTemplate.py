def build_birdhouse(form):
    return {
        "project_type": "birdhouse",
        "dimensions": {
            "width_inches": form.get("widthInches", type=float),
            "depth_inches": form.get("depthInches", type=float),
            "height_inches": form.get("heightInches", type=float),
        },
        "entrance_hole_diameter_inches": form.get("entranceHoleInches", type=float),
        "perch": form.get("perch") == "yes",
        "color": form.get("color", "").strip(),
        "description": form.get("userInput", "").strip(),
    }
