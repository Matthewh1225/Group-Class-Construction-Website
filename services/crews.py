import json

CREW_RATES = {
    "general": {"name": "General labor", "rate": 40},
    "carpenter": {"name": "Carpenters", "rate": 55},
    "mason": {"name": "Concrete & masonry", "rate": 55},
    "roofer": {"name": "Roofers", "rate": 50},
    "electrician": {"name": "Electricians", "rate": 80},
    "plumber": {"name": "Plumbers", "rate": 85},
    "hvac": {"name": "HVAC technicians", "rate": 80},
    "drywall": {"name": "Drywall installers", "rate": 50},
    "painter": {"name": "Painters", "rate": 45},
    "operator": {"name": "Equipment operators", "rate": 70},
    "ironworker": {"name": "Steel & ironworkers", "rate": 70},
    "supervisor": {"name": "Site supervisor", "rate": 90},
}

HOURS_PER_DAY = 8
MAX_WORKERS = 99
MAX_DAYS = 1000


def read_days(value):
    # Equal values mean an exact number of days.
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("The crew's working days are missing.")
    low = value[0]
    high = value[1]
    if type(low) != int or type(high) != int:
        raise ValueError("Working days must be whole numbers.")
    if low < 1 or high < low or high > MAX_DAYS:
        raise ValueError(f"Working days must be between 1 and {MAX_DAYS}.")
    return [low, high]


# Form input arrives as JSON text.
def parse_crew(crew_json):
    try:
        data = json.loads(crew_json or "")
    except ValueError:
        raise ValueError("The crew could not be read. Please choose it again.")
    return check_crew(data)


# Shared by the crew form and the AI planner.
def check_crew(data):
    if not isinstance(data, dict) or not isinstance(data.get("members"), list):
        raise ValueError("The crew could not be read. Please choose it again.")

    label = data.get("label")
    if not isinstance(label, str) or label.strip() == "" or len(label) > 120:
        raise ValueError("The crew needs a short name.")

    members = []
    roles = set()
    for member in data["members"]:
        if not isinstance(member, dict) or not isinstance(member.get("role"), str) or member["role"] not in CREW_RATES:
            raise ValueError("The crew includes an unknown specialty.")
        if member["role"] in roles:
            raise ValueError("Each specialty can only appear once.")
        roles.add(member["role"])
        workers = member.get("workers")
        if type(workers) != int or workers < 1 or workers > MAX_WORKERS:
            raise ValueError(f"Each specialty needs between 1 and {MAX_WORKERS} workers.")
        members.append({"role": member["role"], "workers": workers, "days": read_days(member.get("days"))})
    if len(members) == 0:
        raise ValueError("Add at least one worker to the crew.")

    days = read_days(data.get("days"))
    if any(member["days"][1] > days[1] for member in members):
        raise ValueError("A role's working days cannot exceed the project's maximum days.")
    return {"label": label.strip(), "days": days, "members": members}


def money(value):
    return "${:,.0f}".format(value)


def range_text(low, high):
    if low == high:
        return low
    return low + " – " + high


def crew_estimate(crew):
    rows = []
    total_workers = 0
    total_hourly = 0
    total_low = 0
    total_high = 0
    for member in crew["members"]:
        specialty = CREW_RATES[member["role"]]
        shortest, longest = member["days"]
        hourly = member["workers"] * specialty["rate"]
        low = hourly * HOURS_PER_DAY * shortest
        high = hourly * HOURS_PER_DAY * longest
        rows.append({
            "name": specialty["name"],
            "workers": member["workers"],
            "rate": money(specialty["rate"]),
            "hourly": money(hourly),
            "days": range_text(f"{shortest:,}", f"{longest:,}") + " days",
            "cost": range_text(money(low), money(high)),
        })
        total_workers = total_workers + member["workers"]
        total_hourly = total_hourly + hourly
        total_low = total_low + low
        total_high = total_high + high

    shortest, longest = crew["days"]
    return {
        "label": crew["label"],
        "rows": rows,
        "workers": total_workers,
        "hourly": money(total_hourly),
        "days": range_text(f"{shortest:,}", f"{longest:,}") + " working days",
        "cost": range_text(money(total_low), money(total_high)),
    }
