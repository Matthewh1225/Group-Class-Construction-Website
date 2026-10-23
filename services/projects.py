PROJECT_STATUS_LABELS = {"Review Needed": "Partial result"}

def default_project_name(job):
    # TODO: Suggest a short project name using the description or project type.
    pass
def can_save_project(job):
    # TODO: Check that the plan is finished and has materials before allowing it to be saved.
    pass


def save_job_as_project(user_id, job, name):
    # TODO: Save a link to the user's finished plan, checking the name and avoiding duplicate saves.
    pass


def get_project_list(user_id, limit=None, search="", status=""):
    # TODO: Get the user's saved plans, apply the search and status filters, and show recent ones first.
    pass


def count_projects(user_id):
    # TODO: Count how many projects this user has saved.
    pass


def get_project_details(project_id, user_id):
    # TODO: Get this user's saved project, its plan, status label, and any saved crew.
    pass


def get_project_saved_from_job(job_id, user_id):
    # TODO: Find the user's saved project and crew for this planning job, if one exists.
    pass


def rename_project(project_id, user_id, name):
    # TODO: Check the new name and update it only for a project that belongs to this user.
    pass


def set_project_completed(project_id, user_id, completed):
    # TODO: Mark the user's project as completed or reopen it.
    pass


def save_project_crew(project_id, user_id, crew):
    # TODO: Check and save the crew for the user's project
    pass


def delete_project(project_id, user_id):
    # TODO: Remove the user's saved project without deleting the original planning history.
    pass
