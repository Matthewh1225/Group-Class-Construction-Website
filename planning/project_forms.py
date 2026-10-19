import math


def read_number(form, name, label, minimum, whole=False):
    number_type = int if whole else float
    value = form.get(name, type=number_type)
    if value is None or (not whole and not math.isfinite(value)):
        kind = "whole number" if whole else "number"
        raise ValueError(f"Enter a valid {kind} for {label}.")
    if value < minimum:
        raise ValueError(f"{label.capitalize()} must be at least {minimum}.")
    return value


# Reads a dropdown or yes/no answer
def read_choice(form, name, label, choices):
    value = form.get(name)
    if value not in choices:
        raise ValueError(f"Choose a valid option for {label}.")
    return value


def read_text(form, name, label, required=False):
    value = form.get(name, "").strip()
    if not value:
        if required:
            raise ValueError(f"Enter {label}.")
        return None
    return value


# Each function turns one project template into a project dict.
def build_birdhouse(form):
    return {
        "project_type": "birdhouse",
        "dimensions": {
            "width_inches": read_number(form, "widthInches", "width", 1),
            "depth_inches": read_number(form, "depthInches", "depth", 1),
            "height_inches": read_number(form, "heightInches", "height", 1),
        },
        "entrance_hole_diameter_inches": read_number(form, "entranceHoleInches", "entrance hole diameter", 0.5),
        "perch": read_choice(form, "perch", "perch", ("yes", "no")) == "yes",
        "color": read_text(form, "color", "a birdhouse color", required=True),
        "description": read_text(form, "userInput", "a project description", required=True),
    }


def build_shed(form):
    description = read_text(form, "userInput", "a project description")
    if not description:
        raise ValueError("Describe the storage shed you want to build.")

    return {
        "project_type": "shed",
        "dimensions": {
            "length_ft": read_number(form, "lengthFt", "length", 1),
            "width_ft": read_number(form, "widthFt", "width", 1),
            "height_ft": read_number(form, "heightFt", "height", 1),
        },
        "ramp": read_choice(form, "ramp", "ramp", ("yes", "no")) == "yes",
        "window": read_choice(form, "window", "window", ("yes", "no")) == "yes",
        "air_conditioning": read_choice(form, "ac", "air conditioning", ("yes", "no")) == "yes",
        "lighting": read_choice(form, "lighting", "lighting", ("yes", "no")) == "yes",
        "description": description,
    }


def build_deck(form):
    return {
        "project_type": "deck",
        "dimensions": {
            "length_ft": read_number(form, "lengthFt", "length", 1),
            "width_ft": read_number(form, "widthFt", "width", 1),
            "height_ft": read_number(form, "heightFt", "height above ground", 0),
        },
        "decking": read_choice(form, "decking", "decking material", ("pressure-treated wood", "cedar")),
        "railing": read_choice(form, "railing", "railing", ("yes", "no")) == "yes",
        "stairs": read_choice(form, "stairs", "stairs", ("yes", "no")) == "yes",
        "description": read_text(form, "userInput", "a project description"),
    }


def build_residential_building(form):
    return {
        "project_type": "residential_building",
        "floors": read_number(form, "floors", "floors", 1, whole=True),
        "bedrooms": read_number(form, "bedrooms", "bedrooms", 0, whole=True),
        "bathrooms": read_number(form, "bathrooms", "bathrooms", 0, whole=True),
        "description": read_text(form, "userInput", "a project description"),
    }


def build_commercial_building(form):
    return {
        "project_type": "commercial_building",
        "floors": read_number(form, "floors", "floors", 1, whole=True),
        "rooms": read_number(form, "rooms", "rooms", 1, whole=True),
        "elevator": read_choice(form, "elevator", "elevator", ("yes", "no")) == "yes",
        "description": read_text(form, "userInput", "a project description"),
    }


def build_custom_project(form):
    description = read_text(form, "userInput", "a project description")
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
