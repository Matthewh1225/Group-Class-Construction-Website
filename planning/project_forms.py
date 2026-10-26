import math


def read_number(form, name, label, minimum, whole=False, default=None):
    if not form.get(name, "").strip() and default is not None:
        return default
    number_type = int if whole else float
    value = form.get(name, type=number_type)
    if value is None or (not whole and not math.isfinite(value)):
        kind = "whole number" if whole else "number"
        raise ValueError(f"Enter a valid {kind} for {label}.")
    if value < minimum:
        raise ValueError(f"{label.capitalize()} must be at least {minimum}.")
    return value


def read_choice(form, name, label, choices=("no", "yes")):
    value = form.get(name, choices[0])
    if value not in choices:
        raise ValueError(f"Choose a valid option for {label}.")
    return value


def build_birdhouse(form):
    return {
        "project_type": "birdhouse",
        "dimensions": {
            "width_inches": read_number(form, "widthInches", "width", 1),
            "depth_inches": read_number(form, "depthInches", "depth", 1),
            "height_inches": read_number(form, "heightInches", "height", 1),
        },
        "entrance_hole_diameter_inches": read_number(form, "entranceHoleInches", "entrance hole diameter", 0.5, default=1.5),
        "perch": read_choice(form, "perch", "perch") == "yes",
        "color": form.get("color", "").strip() or "natural wood",
    }


def build_shed(form):
    return {
        "project_type": "shed",
        "dimensions": {
            "length_ft": read_number(form, "lengthFt", "length", 1),
            "width_ft": read_number(form, "widthFt", "width", 1),
            "height_ft": read_number(form, "heightFt", "height", 1, default=8),
        },
        "ramp": read_choice(form, "ramp", "ramp") == "yes",
        "window": read_choice(form, "window", "window") == "yes",
        "air_conditioning": read_choice(form, "ac", "air conditioning") == "yes",
        "lighting": read_choice(form, "lighting", "lighting") == "yes",
    }


def build_bathroom_remodel(form):
    length = read_number(form, "lengthFt", "length", 3)
    width = read_number(form, "widthFt", "width", 3)
    shower = read_choice(form, "newShower", "shower") == "yes"
    bathtub = read_choice(form, "newBathtub", "bathtub") == "yes"
    wall_tile = read_choice(form, "wallTile", "wall tile",
                            ("shower or tub area only", "all walls", "none"))
    return {
        "project_type": "bathroom_remodel",
        "dimensions": {
            "length_ft": length,
            "width_ft": width,
            "height_ft": read_number(form, "heightFt", "ceiling height", 6, default=8),
        },
        "floor_area_sq_ft": round(length * width, 1),
        "new_shower": shower,
        "new_bathtub": bathtub,
        "new_toilet": read_choice(form, "newToilet", "toilet") == "yes",
        "vanity": read_choice(form, "vanity", "vanity", ("single sink", "double sink", "none")),
        "flooring": read_choice(form, "flooring", "flooring",
                                ("porcelain tile", "ceramic tile", "vinyl plank", "keep existing floor")),
        "wall_tile": wall_tile,
        "drywall": read_choice(form, "drywall", "drywall",
                               ("patch and repair", "replace walls and ceiling", "none")),
        "waterproofing": shower or bathtub or wall_tile != "none",
        "painting": read_choice(form, "painting", "painting") == "yes",
        "finishing_trim_and_accessories": read_choice(form, "finishing", "finishing") == "yes",
        "plumbing": read_choice(form, "plumbing", "plumbing",
                                ("fixtures stay in place", "move or add lines", "none")),
        "electrical": read_choice(form, "electrical", "electrical",
                                  ("lighting and exhaust fan", "lighting, fan and new outlets", "none")),
    }


def build_residential_building(form):
    return {
        "project_type": "residential_building",
        "footprint_sq_ft": read_number(form, "footprintSqFt", "ground-floor area", 1),
        "floors": read_number(form, "floors", "floors", 1, whole=True, default=1),
        "bedrooms": read_number(form, "bedrooms", "bedrooms", 0, whole=True),
        "bathrooms": read_number(form, "bathrooms", "bathrooms", 0, whole=True),
    }


def build_commercial_building(form):
    return {
        "project_type": "commercial_building",
        "footprint_sq_ft": read_number(form, "footprintSqFt", "ground-floor area", 1),
        "floors": read_number(form, "floors", "floors", 1, whole=True, default=1),
        "rooms": read_number(form, "rooms", "rooms", 1, whole=True),
        "elevator": read_choice(form, "elevator", "elevator") == "yes",
    }


PROJECT_SIZES = {
    "small": "Birdhouse, planter, shelf",
    "medium": "Shed, workbench, fence run",
    "large": "Deck, garage, addition",
    "mega": "Whole buildings",
}


PROJECT_TEMPLATES = {
    "birdhouse": {
        "art": "M76 62V86M84 62V86M56 62H104M60 62V36H100V62M52 40L80 18L108 40M74 47a6 6 0 1 0 12 0a6 6 0 1 0-12 0",
        "description": "Size, with optional perch and finish",
        "title": "Birdhouse",
        "size": "small",
        "form": "project_forms/birdhouse.html",
        "builder": build_birdhouse,
    },
    "shed": {
        "art": "M40 86V50M120 86V50M32 56L80 26L128 56M64 86V60H96V86M80 60V86",
        "description": "Size, with optional ramp, window and utilities",
        "title": "Storage Shed",
        "size": "medium",
        "form": "project_forms/shed.html",
        "builder": build_shed,
    },
    "bathroom_remodel": {
        "art": "M26 56H134M30 56V64Q30 78 46 78H114Q130 78 130 64V56M44 78V86M116 78V86M38 56V44H48M126 18V56M126 18H104M96 24H112L108 31H100ZM100 36V40M104 36V42M108 36V40",
        "description": "Size, tile, fixtures, plumbing and finishes",
        "title": "Bathroom Remodel",
        "size": "medium",
        "form": "project_forms/bathroom_remodel.html",
        "builder": build_bathroom_remodel,
    },
    "residential_building": {
        "art": "M36 86V44M124 86V44M26 50L80 16L134 50M104 33V14H114V40M48 52h14v12H48zM98 52h14v12H98zM48 70h14v12H48zM98 70h14v12H98zM72 86V66H88V86",
        "description": "Ground-floor area, floors, bedrooms and bathrooms",
        "title": "Residential Building",
        "size": "mega",
        "form": "project_forms/residential_building.html",
        "builder": build_residential_building,
    },
    "commercial_building": {
        "art": "M44 86V18H116V86M86 18V10H104V18M52 26h10v10H52zM67 26h10v10H67zM83 26h10v10H83zM98 26h10v10H98zM52 44h10v10H52zM67 44h10v10H67zM83 44h10v10H83zM98 44h10v10H98zM50 64h60v22H50zM70 64v22M90 64v22",
        "description": "Ground-floor area, floors, rooms and elevator",
        "title": "Commercial Building",
        "size": "mega",
        "form": "project_forms/commercial_building.html",
        "builder": build_commercial_building,
    },
}


def build_project(form):
    project_mode = form.get("projectMode")
    project_size = form.get("projectSize")
    project_template = form.get("projectTemplate")
    description = form.get("userInput", "").strip() or None
    if project_mode == "template":
        template = PROJECT_TEMPLATES.get(project_template)
        if template is None:
            raise ValueError("Choose a valid project template.")
        project_size = template["size"]
        project_data = template["builder"](form)
    elif project_mode == "custom":
        if not description:
            raise ValueError("Describe your project first.")
        if project_size not in PROJECT_SIZES:
            raise ValueError("Choose a valid project size.")
        project_template = None
        project_data = {"project_type": "custom"}
    else:
        raise ValueError("Choose a template or custom project.")
    project_data.update({"description": description, "project_mode": project_mode, "project_size": project_size,
                         "project_template": project_template})
    return project_data
