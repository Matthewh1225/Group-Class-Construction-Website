from flask import Blueprint, abort, render_template, request, session

from planning.jobs import get_job
from services.crews import CREW_RATES, HOURS_PER_DAY, MAX_DAYS, MAX_WORKERS
from services.projects import get_project_details

crews_bp = Blueprint("crews", __name__)


@crews_bp.get("/crews")
def crews():
    project = None
    initial_crew = None
    project_id = request.args.get("project_id", type=int)
    job_id = request.args.get("job_id")
    if project_id is not None or job_id:
        if "user_id" not in session:
            abort(401)
    if project_id is not None:
        project = get_project_details(project_id, session["user_id"])
        if project is None:
            abort(404)
        result = project["plan"].get("result") or {}
        initial_crew = project["crew"] or result.get("crew")
    elif job_id:
        job = get_job(job_id, session["user_id"])
        if job is None:
            abort(404)
        result = job["result"] or {}
        initial_crew = result.get("crew")
    crew_data = {"rates": CREW_RATES, "hoursPerDay": HOURS_PER_DAY, "savedCrew": initial_crew}
    return render_template("crews.html", crew_rates=CREW_RATES, crew_data=crew_data,
                           hours_per_day=HOURS_PER_DAY, max_days=MAX_DAYS,
                           max_workers=MAX_WORKERS, project=project)
