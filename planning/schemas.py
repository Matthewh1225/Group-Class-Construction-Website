import logging

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from services.crews import MAX_WORKERS

logger = logging.getLogger(__name__)


class PlanningError(Exception):
    pass


class AnswerFormatError(PlanningError):
    """An invalid AI answer that the stage can retry once."""


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, str_strip_whitespace=True)


class Specification(Record):
    details: list[str]
    questions: list[str]


class Material(Record):
    material_name: str = Field(
        min_length=1, description="One product as a store names it, such as 2x4 stud or Drywall screw."
    )
    specification: str = Field(
        description="Store buying facts only: trade size or dimensions, rating, material and type, "
        "such as '2x4 x 8 ft' or '#6 x 1-1/4 in, coarse thread'. Put use and placement in notes. "
        "Use an empty string if nothing applies."
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


# Old saved plans also have required_specs; they still load because saved JSON isn't validated again.
class AuditedMaterial(Material):
    category: str | None = Field(description="A category from classifications, or null if uncertain.")
    subcategory: str | None = Field(description="A subcategory belonging to that category, or null if uncertain.")
    estimated_unit_price: float = Field(
        ge=0, description="Estimated typical US retail price in US dollars for ONE unit of this "
        "material's unit (not the line total). Always give your best guess; never null."
    )


# Validate crew separately so an invalid recommendation does not reject the materials.
class CrewMember(Record):
    role: str = Field(description="A key from available_crew_roles, such as carpenter.")
    workers: int = Field(ge=1, le=MAX_WORKERS)
    days: list[int] = Field(min_length=2, max_length=2, description="[shortest, longest] whole working days.")


class CrewRecommendation(Record):
    days: list[int] = Field(min_length=2, max_length=2, description="[shortest, longest] whole working days.")
    members: list[CrewMember] = Field(min_length=1)


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


def check_machinery(items, machinery_catalog):
    """Keep valid machinery recommendations and drop the rest with a warning."""
    machinery_ids = set()
    for product in machinery_catalog:
        machinery_ids.add(product["product_id"])

    machinery = []
    seen = set()
    for item in items:
        try:
            machine = MachineryRecommendation.model_validate(item).model_dump()
        except ValidationError:
            logger.warning("Dropping a machinery recommendation with an invalid format.")
            continue
        if machine["product_id"] not in machinery_ids:
            logger.warning("Dropping machinery %s because it is not in the machinery catalog.", machine["product_id"])
            continue
        if machine["product_id"] in seen:
            logger.warning("Dropping repeated machinery %s.", machine["product_id"])
            continue
        seen.add(machine["product_id"])
        machinery.append(machine)
    return machinery


def merge_catalog_matches(estimate, matching, material_candidates, machinery_catalog):
    """Accept only selections from each material's own shortlist."""
    if (not isinstance(matching, dict) or not isinstance(matching.get("matches"), list)
            or not isinstance(matching.get("machinery"), list)):
        raise AnswerFormatError("the answer did not include matches and machinery lists")

    allowed_ids = {group["material_index"]: {product["product_id"] for product in group["candidates"]}
                   for group in material_candidates}

    material_count = len(estimate["materials"])
    chosen = {}  # material index -> checked match
    for item in matching["matches"]:
        try:
            match = MaterialMatch.model_validate(item).model_dump()
        except ValidationError:
            logger.warning("Ignoring a Matcher match with an invalid format.")
            continue
        index = match["material_index"]
        if index >= material_count:
            logger.warning("Ignoring a Matcher match for unknown material %s.", index)
            continue
        if index in chosen:
            logger.warning("Ignoring a repeated Matcher match for material %s; keeping the first one.", index)
            continue
        product_id = match["product_id"]
        if product_id is not None and product_id not in allowed_ids.get(index, ()):
            logger.warning("Ignoring product %s outside the shortlist for material %s.", product_id, index)
            product_id = None
        chosen[index] = product_id

    # Copy each material to keep the original estimate unchanged.
    result = dict(estimate)
    result["materials"] = []
    for index, material in enumerate(estimate["materials"]):
        material = dict(material)
        material["product_id"] = chosen.get(index)
        result["materials"].append(material)
    result["machinery"] = check_machinery(matching["machinery"], machinery_catalog)
    return result
