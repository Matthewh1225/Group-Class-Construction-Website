"""AI answer formats and basic checks."""

import math

from pydantic import BaseModel, ConfigDict, Field


# Bad AI answers get one more try in the workflow.
class BadAnswer(Exception):
    pass


# These classes tell the AI what to return and check its answer.
class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Specification(Record):
    details: list[str]
    questions: list[str]


class Material(Record):
    material_name: str = Field(min_length=1)
    specification: str
    quantity: float = Field(
        gt=0, description="Positive estimated amount, including waste and rounding. "
        "Use labeled assumptions when measurements are missing; never null or zero."
    )
    unit: str = Field(min_length=1)
    notes: str
    product_id: int | None


class DraftEstimate(Record):
    materials: list[Material]


class CrewMember(Record):
    role: str
    workers: int = Field(ge=1)
    days: list[int] = Field(min_length=2, max_length=2)


class CrewRecommendation(Record):
    days: list[int] = Field(min_length=2, max_length=2)
    members: list[CrewMember] = Field(min_length=1)


class AuditedEstimate(DraftEstimate):
    summary: str
    notes: list[str]
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


# Clear product IDs outside the supplied catalog.
def check_estimate(estimate, catalog_ids):
    if not estimate["materials"]:
        raise BadAnswer("The estimate has no materials.")
    for material in estimate["materials"]:
        if not material["material_name"].strip() or not material["unit"].strip():
            raise BadAnswer("Material names and units cannot be blank.")
        if not math.isfinite(material["quantity"]) or material["quantity"] <= 0:
            raise BadAnswer(f"{material['material_name']}: the estimated quantity must be greater than zero.")
        if not material["notes"].strip():
            raise BadAnswer(f"{material['material_name']}: explain the estimated quantity in notes.")
        if material["product_id"] not in catalog_ids:
            material["product_id"] = None
    return estimate
