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
