"""
The planner's result format, and the checks run on every answer an AI model sends back.

Every estimate stage (planner, Pro's second planner, auditor) returns the same dictionary,
the job stores it as job["result"], and the result pages read it directly:

    result = {
        "planning_status": "complete",   # or "partial" when any quantity is unknown (added by Python)
        "summary": "A 12 x 16 ft pressure-treated deck ...",
        "materials": [material, ...],
        "assumptions": ["Joists 16 in on center", ...],
        "warnings": ["Footing design must be verified locally", ...],
    }

    material = {
        "material_name": "Pressure-treated deck board",
        "specification": "5/4 x 6 in x 16 ft",
        "quantity": 48,          # amount the project NEEDS, in unit (waste included); None = unknown
        "unit": "piece",
        "waste_percent": 10,
        "round_up": True,
        "calculation": {"method": "count", "inputs": [{"name": "count", "value": 44, "unit": "piece"}]},
        "notes": "Why this amount, or what is missing when quantity is None",
        "product_id": 1003,      # products.product_id, kept only if it is in the catalog; otherwise None
    }

quantity is the required amount, never a store purchase amount. How many of a product to buy
is worked out when the page is shown (planning/presentation.py), from product data read
from the database. Product names, prices and stock are never stored here.
docs/database_erd.md maps each field to its database column.

Python recalculates every quantity except "manual" ones. One limit: for a wall or any other
surface that is not a single rectangle, the model works out the area itself and passes it to the
"coverage" method as its "area" input. Python checks the coverage rate, waste and rounding, but
it cannot recheck that area.
"""

import math
from decimal import Decimal, ROUND_CEILING
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# Raised when an AI model's answer cannot be used: it was cut off, it was empty, or its
# numbers do not pass the checks below. workflow.run_stage then asks the model once more.
class BadAnswer(Exception):
    pass


# These Pydantic classes describe the JSON the AI models must return. They are used in only
# two places (planning/workflow.py): to send the JSON schema to the model, and to check the
# model's answer when it arrives. After that check the answer is a plain dictionary.
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
    quantity: float | None = Field(ge=0)
    unit: str = Field(min_length=1)
    waste_percent: float = Field(ge=0, le=100)
    round_up: bool
    calculation: Calculation
    notes: str
    product_id: int | None


class Estimate(Record):
    summary: str
    materials: list[Material]
    assumptions: list[str]
    warnings: list[str]


# Makes unit names consistent, for example "Feet" and "foot" both become "ft".
def normalize_unit(unit):
    aliases = {"feet": "ft", "foot": "ft", "inches": "in", "inch": "in",
               "meters": "m", "metres": "m", "square feet": "sq_ft", "sq ft": "sq_ft",
               "square meters": "sq_m", "sq m": "sq_m", "layers": "count",
               "layer": "count", "coats": "count", "coat": "count",
               "gallons": "gallon", "sheets": "sheet", "pieces": "piece",
               "rolls": "roll", "screws": "screw", "boxes": "box", "bags": "bag"}
    text = unit.strip().lower()
    return aliases.get(text, text)


# Converts a length from one unit to another (ft, in, m, cm), for example 12 in to ft.
def length_in(value, unit, target):
    factors = {"ft": Decimal("0.3048"), "in": Decimal("0.0254"),
               "m": Decimal("1"), "cm": Decimal("0.01")}
    if unit not in factors or target not in factors:
        raise BadAnswer("A length must use ft, in, m or cm.")
    return value * factors[unit] / factors[target]


# Converts an area from one unit to another (sq_ft or sq_m).
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


# Checks a material has exactly the inputs its calculation method needs. Returns them as {name: (value, unit)}.
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


# The "layers" input (for example 2 coats of paint) as a number. It must use count units.
def layer_count(inputs):
    layers, layers_unit = inputs["layers"]
    if layers_unit != "count":
        raise BadAnswer("Layers must use count units.")
    return layers


# Works out the amount before waste and rounding. inputs maps each input name to (Decimal value, unit).
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
        # 2 x (length + width), in the material's length unit
        length = length_in(*inputs["length"], unit)
        width = length_in(*inputs["width"], unit)
        return 2 * (length + width)

    if method == "rectangle_area":
        # length x width x layers, in the material's area unit
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

    # coverage: area x layers / coverage rate, for example 400 sq_ft x 2 coats / 400 sq_ft/gallon = 2 gallon.
    # The rate must be area per one material unit ("sq_ft/sheet" for sheets), and the rate decides the area unit.
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


# Returns the material's final quantity: Python's own calculation, or the model's number for "manual".
def calculate_quantity(material):
    inputs = validated_inputs(material)
    if material["calculation"]["method"] == "manual":
        # A manual quantity (or a None quantity) must say where it came from or what is missing.
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


# Checks an estimate dict from an AI model and fixes what Python can work out itself:
# - each quantity is replaced by the one Python calculates
# - a product_id that is not in catalog_ids (the store catalog) is removed (set to None)
# Raises BadAnswer when the estimate cannot be used; the model is then asked again.
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
