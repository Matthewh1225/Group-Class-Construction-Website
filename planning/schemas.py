
import logging

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class PlanningError(Exception):
    pass


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, str_strip_whitespace=True)


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
        description="Always include this field as null. The later Matcher assigns catalog IDs."
    )


class DraftEstimate(Record):
    materials: list[Material] = Field(min_length=1)


class AuditedMaterial(Material):
    category: str | None = Field(description="A category from classifications, or null if uncertain.")
    subcategory: str | None = Field(description="A subcategory belonging to that category, or null if uncertain.")


class CrewMember(Record):
    role: str
    workers: int = Field(ge=0)
    days: list[int] = Field(min_length=0, max_length=2)


class CrewRecommendation(Record):
    days: list[int] = Field(min_length=0, max_length=2)
    members: list[CrewMember] = Field(min_length=0)


class AuditedEstimate(DraftEstimate):
    materials: list[AuditedMaterial] = Field(min_length=1)
    summary: str
    notes: list[str]
    crew: CrewRecommendation | None = Field(
        description="Crew recommendation, or null if no crew was estimated."
    )


class MaterialMatch(Record):
    material_index: int = Field(ge=0)
    product_id: int | None = Field(gt=0)


class MachineryRecommendation(Record):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0)
    required: bool
    justification: str = Field(min_length=1)


class CatalogMatches(Record):
    matches: list[MaterialMatch]
    machinery: list[MachineryRecommendation]


def merge_catalog_matches(estimate, matching, material_candidates, machinery_catalog):
    material_ids = {}
    for group in material_candidates:
        allowed_ids = set()
        for product in group["candidates"]:
            allowed_ids.add(product["product_id"])
        material_ids[group["material_index"]] = allowed_ids

    machinery_ids = set()
    for product in machinery_catalog:
        machinery_ids.add(product["product_id"])
    material_count = len(estimate["materials"])
    if len(matching["matches"]) != material_count:
        raise ValueError("The Matcher must return one match or null for every material")
    seen = set()
    for match in matching["matches"]:
        index = match["material_index"]
        if index < 0 or index >= material_count or index in seen:
            raise ValueError("The Matcher returned an invalid or repeated material index")
        seen.add(index)
        allowed_ids = material_ids.get(index, set())
        chosen_id = match["product_id"]
        # Leave invalid product picks unmatched.
        if chosen_id is not None and chosen_id not in allowed_ids:
            logger.warning("Matcher picked product %s outside the candidates for material %s; leaving it unmatched.",
                           chosen_id, index)
            match["product_id"] = None
    seen = set()
    for machine in matching["machinery"]:
        product_id = machine["product_id"]
        if product_id not in machinery_ids:
            raise ValueError("The Matcher returned a machinery ID outside the supplied machinery catalog")
        if product_id in seen:
            raise ValueError("The Matcher recommended the same machine more than once")
        seen.add(product_id)

    # Copy materials before adding product IDs and machinery.
    result = dict(estimate)
    result["materials"] = []
    for material in estimate["materials"]:
        result["materials"].append(dict(material))
    for match in matching["matches"]:
        result["materials"][match["material_index"]]["product_id"] = match["product_id"]
    result["machinery"] = matching["machinery"]
    return result
