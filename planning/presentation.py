# Display helpers only. Saved plans and calculated quantities are never changed.

from decimal import Decimal, InvalidOperation

from .project_forms import PROJECT_TEMPLATES


# Plans are rendered while they are still being built, so missing values become
# an empty dict, list, or string until that stage finishes.
def mapping(value):
    if isinstance(value, dict):
        return value
    return {}

def records(value):
    # only the dictionaries in a list
    result = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                result.append(item)
    return result


def text(value):
    if isinstance(value, str):
        return value.strip()
    return ""


def same_text_key(message):
    # Two messages count as the same if they only differ in spacing or capitals.
    return " ".join(message.split()).casefold()


def messages(*values):
    # Join several message lists (or single messages) into one list without repeats.
    result = []
    seen = set()
    for value in values:
        if not isinstance(value, list):
            value = [value]
        for item in value:
            message = text(item)
            key = same_text_key(message)
            if message and key not in seen:
                result.append(message)
                seen.add(key)
    return result


UNIT_LABELS = {
    "sq_ft": "sq ft", "sq_m": "sq m", "square feet": "sq ft",
    "square meters": "sq m", "feet": "ft", "inches": "in",
    "fl_oz": "fl oz", "fluid ounces": "fl oz", "gallon": "gal", "gallons": "gal",
}


def read_number(value):
    # The value as a Decimal, or None when it is not a usable non-negative number.
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        # for example a model wrote "about 12"
        return None
    if not number.is_finite() or number < 0:
        return None
    return number


def display_quantity(value, unit="", manual=False):
    # Round for display only; the original number is kept for the detail panel.
    unit = text(unit)
    unit = UNIT_LABELS.get(unit.lower(), unit)
    number = read_number(value)

    if number is None:
        original = "Not supplied"
        if value is not None:
            original = str(value)
        return {"value": "Not determined", "unit": unit, "approximate": False,
                "original": original, "known": False}

    # Two decimals avoid long floating-point tails. Tiny amounts must not look like zero.
    if 0 < number < Decimal("0.01"):
        shown = "<0.01"
        rounded = True
    else:
        shown = format(number, ",.2f").rstrip("0").rstrip(".")
        rounded = Decimal(shown.replace(",", "")) != number
    return {"value": shown, "unit": unit, "approximate": manual or rounded,
            "original": str(value), "known": True}


# Builds one display row per material for the plan's materials table.
def material_rows(estimate):
    rows = []
    for index, item in enumerate(records(mapping(estimate).get("materials"))):
        calculation = mapping(item.get("calculation"))
        method = text(calculation.get("method"))
        manual = method == "manual"
        quantity = display_quantity(item.get("quantity"), item.get("unit"), manual)
        rows.append({
            "name": text(item.get("name")) or f"Material {index + 1}",
            "specification": text(item.get("specification")), "notes": text(item.get("notes")),
            "quantity": quantity, "method": method.replace("_", " ") or "Not provided",
            "inputs": records(calculation.get("inputs")),
            "waste": display_quantity(item.get("waste_percent"), "%"),
        })
    return rows


# Builds the "Project details" list shown on the plan: the user's own form values, or the AI's interpretation.
def project_specs(project, specification, answers):
    specs = []
    if not answers:
        # Only structured user-supplied fields are presented as submitted specifications.
        fields = {**mapping(project.get("dimensions")), **project}
        ignored = {"dimensions", "description", "project_type", "project_mode", "project_size", "project_template"}
        for key, value in fields.items():
            if key in ignored or value is None or value == "" or isinstance(value, (dict, list)):
                continue
            label = key.replace("_", " ").capitalize()
            unit = ""
            for suffix, unit_name in [("_inches", "in"), ("_ft", "ft"), ("_m", "m")]:
                if key.endswith(suffix):
                    label = key[:-len(suffix)].replace("_", " ").capitalize()
                    unit = unit_name
                    break
            if value is True:
                value = "Yes"
            elif value is False:
                value = "No"
            elif isinstance(value, (int, float)):
                quantity = display_quantity(value, unit)
                value = quantity["value"]
                if quantity["unit"]:
                    value = value + " " + quantity["unit"]
            specs.append({"label": label, "value": str(value), "source": "From your request"})
    if not specs:
        for detail in messages(specification.get("details")):
            if detail.casefold().startswith("assumption:"):
                continue
            # "Length: 12 ft" becomes label "Length", value "12 ft"; anything else is one value
            label, separator, value = detail.partition(":")
            if separator and len(label) < 45:
                specs.append({"label": label, "value": value.strip(), "source": "Planner interpretation"})
            else:
                specs.append({"label": "Project detail", "value": detail, "source": "Planner interpretation"})
    return specs


STATUS_LABELS = {
    "queued": ("Queued for planning", "neutral"),
    "running": ("Preparing your plan", "neutral"),
    "needs_input": ("Details needed", "attention"),
    "failed": ("Processing stopped", "attention"),
    "cancelled": ("Cancelled", "neutral"),
    "partial": ("Partial result", "neutral"),
    "complete": ("Complete", "ready"),
}


def status_label(job):
    status = job.get("status")
    return STATUS_LABELS.get(status, ("Status unavailable", "neutral"))


def review_reason(job, rows, questions):
    if job.get("status") != "partial":
        return ""
    unknown = 0
    for row in rows:
        if not row["quantity"]["known"]:
            unknown = unknown + 1
    if unknown == 1:
        return "1 material quantity could not be determined from the details given."
    if unknown > 1:
        return f"{unknown} material quantities could not be determined from the details given."
    if questions:
        return "Some project details still need confirmation; see Assumptions & Unresolved Details."
    return "This saved estimate was marked for review. Check its assumptions and details before using it."


def plan_presentation(job):
    result = mapping(job.get("result"))
    estimate = mapping(result.get("estimate"))
    project = mapping(job.get("project"))
    specification = mapping(job.get("specification"))
    rows = material_rows(estimate)
    project_type = text(project.get("project_type"))
    title = PROJECT_TEMPLATES.get(project_type, {}).get("title", "Your project") + " plan"
    answers = records(job.get("answers"))
    details = []
    for detail in messages(specification.get("details")):
        if not detail.casefold().startswith("assumption:"):
            details.append(detail)

    # the best short description available
    description = text(estimate.get("summary"))
    if not description:
        description = text(specification.get("summary"))
    if not description:
        description = text(project.get("description"))

    label, tone = status_label(job)
    return {"title": title, "description": description,
            "status_label": label, "status_tone": tone,
            "materials": rows,
            "material_details": [row for row in rows if row["specification"] or row["notes"]],
            "specs": project_specs(project, specification, job.get("answers")),
            "warnings": project_notices(messages(result.get("warnings"), estimate.get("warnings"))),
            "assumptions": assumptions,
            "questions": questions, "details": details,
            "request": text(project.get("description")), "answers": answers}
