from flask import Blueprint, render_template, request, session

from services.crews import CREW_RATES, HOURS_PER_DAY
from services.projects import get_project

crews_bp = Blueprint("crews", __name__)


@crews_bp.get("/crews")
def crews():
    # Project presets live in static/js/crews.js; rates come from services/crews.py.
    # Quote requests need services.rentals.request_crew, which is still a stub.
    # Opened from a saved project (/crews?project_id=5), the page also offers "Save crew to project".
    # get_project only returns the signed-in user's own project.
    project = None
    project_id = request.args.get("project_id", type=int)
    if project_id is not None and "user_id" in session:
        project = get_project(project_id, session["user_id"])
    return render_template("crews.html", crew_rates=CREW_RATES,
                           hours_per_day=HOURS_PER_DAY, project=project)
