"Crew and equipment bookings are not written yet."


def get_available_offerings(starts_at, ends_at, offering_type=None):
    "Find crews or equipment available for the requested dates."
    pass


def create_service_booking(user_id, offering_id, booking_data):
    "Check ownership and availability before saving, in the same database update."
    pass


def get_crews(category_id=None, project_size=None, filters=None, page=1):
    "Find real crews suited to the project type and size."
    pass


def get_crew_details(crew_id):
    "Include the crew's profile, qualifications and equipment."
    pass


def request_crew(user_id, project_details):
    "Save a quote request with the project and crew details."
    pass


def calculate_labor_quote(crew_config):
    "Use actual contractor rates for a quote."
    pass
