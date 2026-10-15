"""Future MySQL integration; the existing SQLite planner is unchanged."""


def save_planner_result(user_id, job_id, plan_version, project_id=None):
    """Validate ownership and save a result, project, and material list once."""
    pass


def get_saved_planner_results(user_id, project_id):
    """Retrieve result versions belonging to the user's project."""
    pass
