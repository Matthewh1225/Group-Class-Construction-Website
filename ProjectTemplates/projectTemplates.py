from .birdhouseTemplate import build_birdhouse
from .commercialBuilding import build_commercial_building
from .deckTemplate import build_deck
from .residentialBuilding import build_residential_building
from .shedTemplate import build_shed


PROJECT_TEMPLATES = {
    "birdhouse": {
        "title": "Birdhouse",
        "size": "small",
        "form": "project_forms/birdhouse.html",
        "handler": build_birdhouse,
    },
    "shed": {
        "title": "Storage Shed",
        "size": "medium",
        "form": "project_forms/shed.html",
        "handler": build_shed,
    },
    "deck": {
        "title": "Outdoor Deck",
        "size": "large",
        "form": "project_forms/deck.html",
        "handler": build_deck,
    },
    "residential_building": {
        "title": "Residential Building",
        "size": "mega",
        "form": "project_forms/residential_building.html",
        "handler": build_residential_building,
    },
    "commercial_building": {
        "title": "Commercial Building",
        "size": "mega",
        "form": "project_forms/commercial_building.html",
        "handler": build_commercial_building,
    },
}
