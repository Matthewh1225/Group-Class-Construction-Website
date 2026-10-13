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


def build_shed(form):
    description = form.get("userInput", "").strip()
    if not description:
        raise ValueError("Describe the storage shed you want to build.")

    return {
        "project_type": "shed",
        "dimensions": {
            "length_ft": form.get("lengthFt", type=float),
            "width_ft": form.get("widthFt", type=float),
            "height_ft": form.get("heightFt", type=float),
        },
        "ramp": form.get("ramp") == "yes",
        "window": form.get("window") == "yes",
        "air_conditioning": form.get("ac") == "yes",
        "lighting": form.get("lighting") == "yes",
        "description": description,
    }


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


def build_residential_building(form):
    return {
        "project_type": "residential_building",
        "floors": form.get("floors", type=int),
        "bedrooms": form.get("bedrooms", type=int),
        "bathrooms": form.get("bathrooms", type=int),
        "description": form.get("userInput", "").strip(),
    }


def build_commercial_building(form):
    return {
        "project_type": "commercial_building",
        "floors": form.get("floors", type=int),
        "rooms": form.get("rooms", type=int),
        "elevator": form.get("elevator") == "yes",
        "description": form.get("userInput", "").strip(),
    }


def build_custom_project(form):
    description = form.get("userInput", "").strip()
    if not description:
        raise ValueError("Describe your project first.")
    return {"project_type": "custom", "description": description}


PROJECT_TEMPLATES = {
    "birdhouse": {
        "title": "Birdhouse",
        "size": "small",
        "form": "project_forms/birdhouse.html",
        "builder": build_birdhouse,
    },
    "shed": {
        "title": "Storage Shed",
        "size": "medium",
        "form": "project_forms/shed.html",
        "builder": build_shed,
    },
    "deck": {
        "title": "Outdoor Deck",
        "size": "large",
        "form": "project_forms/deck.html",
        "builder": build_deck,
    },
    "residential_building": {
        "title": "Residential Building",
        "size": "mega",
        "form": "project_forms/residential_building.html",
        "builder": build_residential_building,
    },
    "commercial_building": {
        "title": "Commercial Building",
        "size": "mega",
        "form": "project_forms/commercial_building.html",
        "builder": build_commercial_building,
    },
}
