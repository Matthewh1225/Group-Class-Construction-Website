"Future MySQL integration stubs for copying saved SQLite planner projects into the store schema."


def save_planner_result(user_id, job_id, plan_version, project_id=None):
    "Validate ownership and save a result, project, and material list once."
    pass


def copy_saved_project_to_database(user_id, saved_project_id):
    "Copy a SQLite saved project, its plan, materials and crew into the MySQL project tables. Returns the MySQL project_id."
    pass


def get_saved_planner_results(user_id, project_id):
    "Retrieve result versions belonging to the user's project."
    pass
