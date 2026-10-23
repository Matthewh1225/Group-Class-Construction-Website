"""AI answer formats and the planner's two errors."""

from pydantic import BaseModel, ConfigDict, Field


# A bad AI answer. The workflow sends the message back to the AI on its second try.
class BadAnswer(Exception):
    pass


# The page shows this error to the user.
class PlanningError(Exception):
    pass


# These classes tell the AI what to return and check its answer.
class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False,
                              str_strip_whitespace=True)


class Specification(Record):
    details: list[str]
    questions: list[str]


class Material(Record):
    material_name: str = Field(min_length=1)
    specification: str = Field(
        description="Material size or type as text; use an empty string if not needed."
    )
    quantity: float = Field(
        gt=0, description="Positive estimated amount, including waste and rounding. "
        "Use labeled assumptions when measurements are missing; never null or zero."
    )
    unit: str = Field(
        min_length=1, description="The quantity's unit, such as sheet, ft or bag. Keep it out of quantity."
    )
    notes: str = Field(
        min_length=1, description="One short string explaining the quantity, assumptions, waste and rounding."
    )
    product_id: int | None = Field(
        description="Always include this field. Planners use null; the final auditor uses a matching catalog ID or null."
    )


class DraftEstimate(Record):
    materials: list[Material] = Field(min_length=1)


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


# The schema cannot know the store catalog, so unknown product IDs are cleared here.
def clear_unknown_products(estimate, catalog_ids):
    for material in estimate["materials"]:
        if material["product_id"] not in catalog_ids:
            material["product_id"] = None
