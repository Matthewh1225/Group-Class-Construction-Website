"Notification persistence placeholders; these functions send nothing."


def queue_account_notification(user_id, template_key, payload, deduplication_key):
    "Queue a notification without duplicating a prior request."
    pass


def schedule_project_reminder(user_id, project_id, scheduled_at):
    "Schedule an owned project reminder according to user preferences."
    pass


def update_notification_preferences(user_id, preferences):
    "Save reminder choices and marketing consent."
    pass
