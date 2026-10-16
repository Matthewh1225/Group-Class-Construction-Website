def get_user_material_lists(user_id):
    "Retrieve saved material lists grouped by project."
    pass


def get_project_material_list(project_id, user_id):
    "Retrieve the saved material list for a user's project."
    pass


def get_material_list_items(material_list_id, user_id):
    "Retrieve the items belonging to a saved material list."
    pass


def get_material_list_count(user_id):
    "Count saved material lists belonging to a user."
    pass


def get_project_material_cost(project_id, user_id):
    "Calculate the estimated material cost for a saved project."
    pass


def get_material_matched_product(material_id, user_id):
    "Retrieve a catalog product matched to a saved material."
    pass


def record_material_acquisition(user_id, material_item_id, acquisition_data):
    "Record an owned purchase or return without double counting orders."
    pass
