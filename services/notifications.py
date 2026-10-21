"Notification helpers are not written yet; nothing is sent."


def queue_account_notification(user_id, template_key, payload, deduplication_key):
    "Do not queue the same request twice."
    pass


def schedule_project_reminder(user_id, project_id, scheduled_at):
    "Check the project belongs to the user and respect their reminder choices."
    pass


def update_notification_preferences(user_id, preferences):
    "Save reminder and marketing choices."
    pass
