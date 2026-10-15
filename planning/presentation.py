"""Display helpers only. Saved plans and calculated quantities are never changed."""

from decimal import Decimal, InvalidOperation

from .project_forms import PROJECT_TEMPLATES


def mapping(value):
    return value if isinstance(value, dict) else {}


def records(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def text(value):
    return value.strip() if isinstance(value, str) else ""


def messages(*values):
    """Normalize optional lists and remove repeated messages, preserving order."""
    result = []
    seen = set()
    for value in values:
        for item in value if isinstance(value, list) else [value]:
            message = text(item)
            key = " ".join(message.split()).casefold()
            if message and key not in seen:
                result.append(message)
                seen.add(key)
    return result


def display_quantity(value, unit="", manual=False):
    """Round for display only; retain the original number for the detail panel."""
    labels = {
        "sq_ft": "sq ft", "sq_m": "sq m", "square feet": "sq ft",
        "square meters": "sq m", "feet": "ft", "inches": "in",
        "fl_oz": "fl oz", "fluid ounces": "fl oz", "gallon": "gal", "gallons": "gal",
    }
    unit = labels.get(text(unit).lower(), text(unit))
    try:
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
            raise ValueError()
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            raise ValueError()
        # Fixed decimals avoid long floating-point tails. Tiny amounts must not look like zero.
        if 0 < number < Decimal("0.01"):
            shown = "<0.01"
            rounded = True
        else:
            number_text = format(number, ",.2f")
            shown = number_text.rstrip("0").rstrip(".")
            rounded = Decimal(shown.replace(",", "")) != number
        return {"value": shown, "unit": unit, "approximate": manual or rounded,
                "original": str(value), "known": True}
    except (InvalidOperation, ValueError, TypeError):
        return {"value": "Not determined", "unit": unit, "approximate": False,
                "original": str(value) if value is not None else "Not supplied", "known": False}


CHECKED_METHODS = {"rectangle_area", "wall_area", "coverage", "rectangle_coverage",
                   "wall_coverage", "perimeter", "count"}


def material_rows(estimate):
    rows = []
    for index, item in enumerate(records(mapping(estimate).get("materials"))):
        calculation = mapping(item.get("calculation"))
        method = text(calculation.get("method"))
        manual = method == "manual"
        quantity = display_quantity(item.get("quantity"), item.get("unit"), manual)
        if not quantity["known"]:
            verification = "Quantity not determined"
        elif manual:
            verification = "Manual estimate - not verified"
        elif method in CHECKED_METHODS:
            verification = "Arithmetic checked by Python"
        else:
            verification = "Calculation status unavailable"
        rows.append({
            "name": text(item.get("name")) or f"Material {index + 1}",
            "specification": text(item.get("specification")), "notes": text(item.get("notes")),
            "purpose": text(item.get("purpose")), "kind": text(item.get("kind")),
            "quantity": quantity, "method": method.replace("_", " ") or "Not provided",
            "verification": verification, "manual": manual,
            "inputs": records(calculation.get("inputs")),
            "explanation": text(calculation.get("explanation")),
            "formula": {
                "rectangle_area": "length x width x layers",
                "wall_area": "(2 x (length + width) x height - openings area) x layers",
                "coverage": "area x layers / coverage per unit",
                "rectangle_coverage": "length x width x layers / coverage per unit",
                "wall_coverage": "(2 x (length + width) x height - openings area) x layers / coverage per unit",
                "perimeter": "2 x (length + width)", "count": "count",
            }.get(method, ""),
            "waste": display_quantity(item.get("waste_percent"), "%"),
            "rounding": "Rounded up to whole items" if item.get("round_up") is True else "No whole-item rounding specified",
            "original": item,
        })
    return rows


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
            if isinstance(value, bool):
                value = "Yes" if value else "No"
            elif isinstance(value, (int, float)):
                quantity = display_quantity(value, unit)
                value = quantity["value"] + (" " + quantity["unit"] if quantity["unit"] else "")
            specs.append({"label": label, "value": str(value), "source": "From your request"})
    if not specs:
        for detail in messages(specification.get("details")):
            label, separator, value = detail.partition(":")
            specs.append({"label": label if separator and len(label) < 45 else "Project detail",
                          "value": value.strip() if separator and len(label) < 45 else detail,
                          "source": "Planner interpretation"})
    return specs


def plan_presentation(job):
    result = mapping(job.get("result"))
    estimate = mapping(result.get("estimate"))
    project = mapping(job.get("project") or job.get("original_request"))
    specification = mapping(job.get("specification") or result.get("specification"))
    # Version 2 estimates are saved only after Python validates their calculation methods.
    rows = material_rows(estimate)
    project_type = text(project.get("project_type"))
    title = PROJECT_TEMPLATES.get(project_type, {}).get("title", "Your project") + " plan"
    questions = messages(estimate.get("questions"), specification.get("questions"),
                         [q.get("question") for q in records(job.get("questions"))])
    assumptions = messages(estimate.get("assumptions"), specification.get("assumptions"))
    warnings = messages(result.get("warnings"), estimate.get("warnings"))
    # These exact generated notices are represented by the manual indicator in the table/details.
    manual_notices = {f"{row['name']}: manual estimate; quantity arithmetic is unverified." for row in rows if row["manual"]}
    warnings = [warning for warning in warnings if warning not in manual_notices]
    for row in rows:
        if not row["quantity"]["known"]:
            warnings = messages(warnings, f"{row['name']}: quantity is unknown.")
    if result.get("review_process_degraded") and not any("fallback" in warning.lower() for warning in warnings):
        warnings = messages(warnings, "The planned reviewer was unavailable; a fallback review was used.")
    warnings = messages(warnings, questions)
    status = job.get("status")
    label, tone = {
        "queued": ("Waiting to start", "neutral"), "running": ("Preparing your plan", "neutral"),
        "needs_input": ("Details needed", "attention"), "failed": ("Processing stopped", "attention"),
        "cancelled": ("Cancelled", "neutral"), "partial": ("Review needed", "attention"),
        "complete": ("AI reviewed" if result.get("audited") else "Estimate ready", "ready"),
    }.get(status, ("Status unavailable", "neutral"))
    if status == "complete" and (warnings or result.get("planning_status") == "partial"):
        label, tone = "Review needed", "attention"
    independent = []
    for name, value in mapping(result.get("independent_estimates")).items():
        value = mapping(value)
        proposal = mapping(value.get("estimate")) or value
        independent.append({"label": name.replace("_", " ").capitalize(), "estimate": proposal,
                            "rows": material_rows(proposal)})
    return {"title": title, "description": text(estimate.get("summary")) or text(specification.get("summary")) or text(project.get("description")),
            "status_label": label, "status_tone": tone, "materials": rows,
            "specs": project_specs(project, specification, job.get("answers")),
            "warnings": warnings, "assumptions": assumptions, "questions": questions,
            "details": messages(specification.get("details")), "independent": independent,
            "has_manual": any(row["manual"] for row in rows),
            "request": text(project.get("description")), "answers": records(job.get("answers"))}
