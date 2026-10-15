"""One estimate format for every tier, with Python quantity checks."""

import math
from decimal import Decimal, ROUND_CEILING
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Specification(Record):
    summary: str
    details: list[str]
    questions: list[str]


class CalculationInput(Record):
    name: Literal["length", "width", "height", "area", "openings_area", "layers", "coverage", "count"]
    value: float = Field(ge=0)
    unit: str = Field(min_length=1)


class Calculation(Record):
    method: Literal["rectangle_area", "wall_area", "coverage", "rectangle_coverage",
                    "wall_coverage", "perimeter", "count", "manual"]
    inputs: list[CalculationInput]


class Material(Record):
    name: str = Field(min_length=1)
    specification: str
    quantity: float | None = Field(ge=0)
    unit: str = Field(min_length=1)
    waste_percent: float = Field(ge=0, le=100)
    round_up: bool
    calculation: Calculation
    notes: str


class Estimate(Record):
    summary: str
    materials: list[Material]
    assumptions: list[str]
    questions: list[str]
    warnings: list[str]


def normalize_unit(unit):
    aliases = {"feet": "ft", "foot": "ft", "inches": "in", "inch": "in",
               "meters": "m", "metres": "m", "square feet": "sq_ft", "sq ft": "sq_ft",
               "square meters": "sq_m", "sq m": "sq_m", "layers": "count",
               "layer": "count", "coats": "count", "coat": "count",
               "gallons": "gallon", "sheets": "sheet", "pieces": "piece",
               "rolls": "roll", "screws": "screw"}
    text = unit.strip().lower()
    return aliases.get(text, text)


def length_in(value, unit, target):
    factors = {"ft": Decimal("0.3048"), "in": Decimal("0.0254"),
               "m": Decimal("1"), "cm": Decimal("0.01")}
    if unit not in factors or target not in factors:
        raise ValueError("A length must use ft, in, m or cm.")
    return value * factors[unit] / factors[target]


def area_in(value, unit, target):
    factors = {"sq_ft": Decimal("0.09290304"), "sq_m": Decimal("1")}
    if unit not in factors or target not in factors:
        raise ValueError("An area must use sq_ft or sq_m.")
    return value * factors[unit] / factors[target]


def validated_inputs(material):
    """Check the input names and positive measurements for one method."""
    method = material.calculation.method
    inputs = {item.name: (Decimal(str(item.value)), normalize_unit(item.unit))
              for item in material.calculation.inputs}
    required = {
        "rectangle_area": {"length", "width", "layers"},
        "wall_area": {"length", "width", "height", "openings_area"},
        "coverage": {"area", "layers", "coverage"},
        "rectangle_coverage": {"length", "width", "layers", "coverage"},
        "wall_coverage": {"length", "width", "height", "openings_area", "layers", "coverage"},
        "perimeter": {"length", "width"}, "count": {"count"}, "manual": set(),
    }
    if len(inputs) != len(material.calculation.inputs) or set(inputs) != required[method]:
        raise ValueError(f"{material.name}: {method} requires exactly {sorted(required[method])}.")
    if method != "manual":
        for name, (value, _) in inputs.items():
            if name not in {"count", "openings_area"} and value <= 0:
                raise ValueError(f"{material.name}: {name} must be positive.")
    return inputs


def net_quantity(material, inputs):
    """Convert measurements and calculate the amount before waste."""
    method = material.calculation.method
    unit = normalize_unit(material.unit)
    if method == "count":
        net, input_unit = inputs["count"]
        if input_unit != unit:
            raise ValueError("Count input and material units must match.")
    else:
        area_unit = unit
        if "coverage" in method:
            coverage, rate_unit = inputs["coverage"]
            area_unit, separator, output_unit = rate_unit.partition("/")
            area_unit = normalize_unit(area_unit)
            if not separator or normalize_unit(output_unit) != unit or unit in {"sq_ft", "sq_m"}:
                raise ValueError(
                    f"{material.name}: coverage unit '{rate_unit}' cannot produce '{unit}'. "
                    "Use sq_ft/sheet or sq_ft/gallon with the matching output unit. "
                    "For area output use rectangle_area/wall_area; for unsupported rates use manual."
                )
        if method == "perimeter":
            target = unit
        elif area_unit in {"sq_ft", "sq_m"}:
            target = "ft" if area_unit == "sq_ft" else "m"
        else:
            raise ValueError("Area calculations require sq_ft or sq_m.")
        if method == "coverage":
            net = area_in(*inputs["area"], area_unit)
        else:
            length = length_in(*inputs["length"], target)
            width = length_in(*inputs["width"], target)
            net = length * width
            if method == "perimeter":
                net = 2 * (length + width)
            elif method.startswith("wall"):
                height = length_in(*inputs["height"], target)
                net = 2 * (length + width) * height - area_in(*inputs["openings_area"], area_unit)
                if net < 0:
                    raise ValueError("Openings exceed the wall area.")
        if "layers" in inputs:
            layers, layers_unit = inputs["layers"]
            if layers_unit != "count":
                raise ValueError("Layers must use count units.")
            net *= layers
        if "coverage" in method:
            net /= coverage
    return net


def calculate_quantity(material):
    """Return the final quantity; never execute a model-supplied expression."""
    inputs = validated_inputs(material)
    if material.calculation.method == "manual":
        if not material.notes.strip():
            raise ValueError(f"{material.name}: explain a manual estimate in notes.")
        if material.round_up and material.quantity is not None and not material.quantity.is_integer():
            raise ValueError(f"{material.name}: a manual whole-item quantity must be an integer.")
        return material.quantity

    quantity = net_quantity(material, inputs) * (1 + Decimal(str(material.waste_percent)) / 100)
    if material.round_up:
        quantity = quantity.to_integral_value(rounding=ROUND_CEILING)
    result = float(quantity)
    if not math.isfinite(result):
        raise ValueError("Calculated quantity is too large.")
    return result


def check_estimate(estimate):
    """Validate formulas and replace model arithmetic before saving any stage."""
    if not estimate.materials and not estimate.questions:
        raise ValueError("An estimate needs materials or a clarification question.")
    for material in estimate.materials:
        if not material.name.strip() or not material.unit.strip():
            raise ValueError("Material names and units cannot be blank.")
        material.quantity = calculate_quantity(material)
    return estimate
