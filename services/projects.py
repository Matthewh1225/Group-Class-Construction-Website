"Saved project service placeholders."


def can_save(job):
    "Check whether a planner job is ready to save."
    pass

def default_project_name(job):
    "Suggest a name for a planner job."
    pass

def save_project(user_id, job, name):
    "Save a planner job as a project for the user."
    pass

def get_user_projects(user_id, limit=None):
    "Return the projects saved by the user."
    pass

def get_project_count(user_id):
    "Count the projects saved by the user."
    pass

def get_project(project_id, user_id):
    "Return an owned project by its project ID."
    pass

def get_project_for_job(job_id, user_id):
    "Return an owned project saved from a planner job."
    pass

def rename_project(project_id, user_id, name):
    "Rename an owned project."
    pass

def set_project_completed(project_id, user_id, completed):
    "Mark an owned project complete or incomplete."
    pass

def save_project_crew(project_id, user_id, crew):
    "Save the crew estimate for an owned project."
    pass

def delete_project(project_id, user_id):
    "Delete an owned project."
    pass
