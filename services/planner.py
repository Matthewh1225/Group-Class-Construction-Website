"Copying saved planner projects to MySQL is not written yet."


def save_planner_result(user_id, job_id, plan_version, project_id=None):
    "Check ownership and save the result, project and materials once."
    pass


def copy_saved_project_to_database(user_id, saved_project_id):
    "Copy the saved plan, materials and crew to MySQL and return the new project ID."
    pass


def get_saved_planner_results(user_id, project_id):
    "Return plan versions for the user's project."
    pass
