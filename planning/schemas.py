"""AI answer formats and quantity checks.

Quantities describe estimated project needs, not store packs.
Manual amounts come from the AI; other amounts are recalculated here.
Coverage checks cannot verify the surface area worked out by the AI.
"""

import math
from decimal import Decimal, ROUND_CEILING
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# Bad AI answers get one more try in the workflow.
class BadAnswer(Exception):
    pass


# These classes tell the AI what to return and check its answer.
class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Specification(Record):
    summary: str
    details: list[str]
    questions: list[str]


class CalculationInput(Record):
    name: Literal["length", "width", "area", "layers", "coverage", "count"]
    value: float = Field(ge=0)
    unit: str = Field(min_length=1)


class Calculation(Record):
    method: Literal["rectangle_area", "perimeter", "coverage", "count", "manual"]
    inputs: list[CalculationInput]


class Material(Record):
    material_name: str = Field(min_length=1)
    specification: str
    quantity: float = Field(ge=0)
    unit: str = Field(min_length=1)
    waste_percent: float = Field(ge=0, le=100)
    round_up: bool
    calculation: Calculation
    notes: str
    product_id: int | None


class DraftEstimate(Record):
    summary: str
    materials: list[Material]


class Estimate(DraftEstimate):
    assumptions: list[str]
    warnings: list[str]


class CrewMember(Record):
    role: str
    workers: int = Field(ge=1)
    days: list[int] = Field(min_length=2, max_length=2)


class CrewRecommendation(Record):
    label: Literal["AI-estimated crew"]
    days: list[int] = Field(min_length=2, max_length=2)
    members: list[CrewMember] = Field(min_length=1)


class AuditedEstimate(Estimate):
    crew: CrewRecommendation


def normalize_unit(unit):
    aliases = {"feet": "ft", "foot": "ft", "inches": "in", "inch": "in",
               "meters": "m", "metres": "m", "square feet": "sq_ft", "sq ft": "sq_ft",
               "square meters": "sq_m", "sq m": "sq_m", "layers": "count",
               "layer": "count", "coats": "count", "coat": "count",
               "gallons": "gallon", "sheets": "sheet", "pieces": "piece",
               "rolls": "roll", "screws": "screw", "boxes": "box", "bags": "bag"}
    text = unit.strip().lower()
    return aliases.get(text, text)


def length_in(value, unit, target):
    factors = {"ft": Decimal("0.3048"), "in": Decimal("0.0254"),
               "m": Decimal("1"), "cm": Decimal("0.01")}
    if unit not in factors or target not in factors:
        raise BadAnswer("A length must use ft, in, m or cm.")
    return value * factors[unit] / factors[target]


def area_in(value, unit, target):
    factors = {"sq_ft": Decimal("0.09290304"), "sq_m": Decimal("1")}
    if unit not in factors or target not in factors:
        raise BadAnswer("An area must use sq_ft or sq_m.")
    return value * factors[unit] / factors[target]


REQUIRED_INPUTS = {
    "rectangle_area": {"length", "width", "layers"},
    "perimeter": {"length", "width"},
    "coverage": {"area", "layers", "coverage"},
    "count": {"count"},
    "manual": set(),
}


# Each input is stored as (value, unit).
def validated_inputs(material):
    method = material["calculation"]["method"]
    inputs = {}
    for item in material["calculation"]["inputs"]:
        inputs[item["name"]] = (Decimal(str(item["value"])), normalize_unit(item["unit"]))
    required = REQUIRED_INPUTS[method]
    if len(inputs) != len(material["calculation"]["inputs"]) or set(inputs) != required:
        raise BadAnswer(f"{material['material_name']}: {method} requires exactly {sorted(required)}.")
    for name, (value, _) in inputs.items():
        if name != "count" and value <= 0:
            raise BadAnswer(f"{material['material_name']}: {name} must be positive.")
    return inputs


def layer_count(inputs):
    layers, layers_unit = inputs["layers"]
    if layers_unit != "count":
        raise BadAnswer("Layers must use count units.")
    return layers


def net_quantity(material, inputs):
    name = material["material_name"]
    method = material["calculation"]["method"]
    unit = normalize_unit(material["unit"])

    if method == "count":
        count, count_unit = inputs["count"]
        if count_unit != unit:
            raise BadAnswer(f"{name}: the count input and the material must use the same unit.")
        return count

    if method == "perimeter":
        length = length_in(*inputs["length"], unit)
        width = length_in(*inputs["width"], unit)
        return 2 * (length + width)

    if method == "rectangle_area":
        if unit == "sq_ft":
            length_unit = "ft"
        elif unit == "sq_m":
            length_unit = "m"
        else:
            raise BadAnswer(f"{name}: rectangle_area needs a sq_ft or sq_m unit; "
                            "use coverage for sheets, gallons and similar units.")
        length = length_in(*inputs["length"], length_unit)
        width = length_in(*inputs["width"], length_unit)
        return length * width * layer_count(inputs)

    # Coverage is area per item, such as sq_ft/sheet.
    coverage, rate_unit = inputs["coverage"]
    area_unit, slash, output_unit = rate_unit.partition("/")
    area_unit = normalize_unit(area_unit)
    if not slash or normalize_unit(output_unit) != unit or unit in {"sq_ft", "sq_m"}:
        raise BadAnswer(
            f"{name}: coverage unit '{rate_unit}' cannot produce '{unit}'. "
            "Use sq_ft/sheet or sq_ft/gallon with the matching output unit. "
            "For an area result use rectangle_area, or manual for other shapes."
        )
    area = area_in(*inputs["area"], area_unit)
    return area * layer_count(inputs) / coverage


def calculate_quantity(material):
    inputs = validated_inputs(material)
    if material["calculation"]["method"] == "manual":
        # Manual and unknown amounts need an explanation.
        if not material["notes"].strip():
            raise BadAnswer(f"{material['material_name']}: explain a manual or unknown quantity in notes.")
        quantity = material["quantity"]
        if material["round_up"] and quantity is not None and not float(quantity).is_integer():
            raise BadAnswer(f"{material['material_name']}: a manual whole-item quantity must be an integer.")
        return quantity

    quantity = net_quantity(material, inputs) * (1 + Decimal(str(material["waste_percent"])) / 100)
    if material["round_up"]:
        quantity = quantity.to_integral_value(rounding=ROUND_CEILING)
    result = float(quantity)
    if not math.isfinite(result):
        raise BadAnswer("Calculated quantity is too large.")
    return result


# Recalculate amounts and clear product IDs outside the catalog.
def check_estimate(estimate, catalog_ids):
    if not estimate["materials"]:
        raise BadAnswer("The estimate has no materials.")
    for material in estimate["materials"]:
        if not material["material_name"].strip() or not material["unit"].strip():
            raise BadAnswer("Material names and units cannot be blank.")
        material["quantity"] = calculate_quantity(material)
        if material["product_id"] not in catalog_ids:
            material["product_id"] = None
    return estimate
