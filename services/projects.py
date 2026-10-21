"Saved project helpers are not written yet."


def can_save(job):
    "Check that the planner job has a result ready to save."
    pass

def default_project_name(job):
    pass

def save_project(user_id, job, name):
    pass

def get_user_projects(user_id, limit=None):
    pass

def get_project_count(user_id):
    pass

def get_project(project_id, user_id):
    "Only return projects that belong to the user."
    pass

def get_project_for_job(job_id, user_id):
    "Only return saved projects that belong to the user."
    pass

def rename_project(project_id, user_id, name):
    pass

def set_project_completed(project_id, user_id, completed):
    pass

def save_project_crew(project_id, user_id, crew):
    pass

def delete_project(project_id, user_id):
    pass
