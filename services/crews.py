# The rates are illustrative planning assumptions, not quotes from real contractors.
# The Crews page gets CREW_RATES from routes/crews.py, so this is the only place to change a rate.
# Nothing here books a crew or sends a quote request.

import json

CREW_RATES = {
    "general": {"name": "General labor", "rate": 28},
    "carpenter": {"name": "Carpenters", "rate": 42},
    "mason": {"name": "Concrete & masonry", "rate": 45},
    "roofer": {"name": "Roofers", "rate": 38},
    "electrician": {"name": "Electricians", "rate": 55},
    "plumber": {"name": "Plumbers", "rate": 52},
    "hvac": {"name": "HVAC technicians", "rate": 52},
    "drywall": {"name": "Drywall installers", "rate": 36},
    "painter": {"name": "Painters", "rate": 34},
    "operator": {"name": "Equipment operators", "rate": 58},
    "ironworker": {"name": "Steel & ironworkers", "rate": 50},
    "supervisor": {"name": "Site supervisor", "rate": 65},
}

HOURS_PER_DAY = 8
MAX_WORKERS = 99
MAX_DAYS = 1000


def read_days(value):
    # Days are sent as [shortest, longest], for example [7, 10].
    # A custom crew uses the same number twice,  [5, 5].
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("The crew's working days are missing.")
    low = value[0]
    high = value[1]
    if type(low) != int or type(high) != int:
        raise ValueError("Working days must be whole numbers.")
    if low < 1 or high < low or high > MAX_DAYS:
        raise ValueError(f"Working days must be between 1 and {MAX_DAYS}.")
    return [low, high]


# Reads the crew the page sent as JSON then returns a clean crew dict.
# Raises ValueError with a readable message if anything is wrong.
def clean_crew(crew_json):
    try:
        data = json.loads(crew_json or "")
    except ValueError:
        raise ValueError("The crew could not be read. Please choose it again.")
    if not isinstance(data, dict) or not isinstance(data.get("members"), list):
        raise ValueError("The crew could not be read. Please choose it again.")

    label = data.get("label")
    if not isinstance(label, str) or label.strip() == "" or len(label) > 120:
        raise ValueError("The crew needs a short name.")

    members = []
    for member in data["members"]:
        if not isinstance(member, dict) or member.get("role") not in CREW_RATES:
            raise ValueError("The crew includes an unknown specialty.")
        workers = member.get("workers")
        if type(workers) != int or workers < 1 or workers > MAX_WORKERS:
            raise ValueError(f"Each specialty needs between 1 and {MAX_WORKERS} workers.")
        members.append({"role": member["role"], "workers": workers, "days": read_days(member.get("days"))})
    if len(members) == 0:
        raise ValueError("Add at least one worker to the crew.")
    if len(members) > len(CREW_RATES):
        raise ValueError("The crew lists too many specialties.")

    # "preset" and "size" let the Crews page reopen the same preset when editing.
    crew = {"label": label.strip(), "source": "custom", "preset": None, "size": None,
            "days": read_days(data.get("days")), "members": members}
    if data.get("source") == "preset":
        preset = data.get("preset")
        size = data.get("size")
        if isinstance(preset, str) and isinstance(size, str) and len(preset) <= 40 and len(size) <= 40:
            crew["source"] = "preset"
            crew["preset"] = preset
            crew["size"] = size
    return crew


# Whole dollars as text, like 1234 becomes "$1,234".
def money(value):
    return "${:,.0f}".format(value)


# Shows a low-high range as text,one number if low and high match.
def show_range(low, high, before="", after=""):
    text = before + "{:,}".format(low)
    if high != low:
        text = text + " – " + before + "{:,}".format(high)
    return text + after


# Rounds to a whole dollar, or to the nearest $100 for a preset crew 
def round_cost(value, crew):
    if crew["source"] == "preset":
        return int(value / 100 + 0.5) * 100
    return int(value + 0.5)


# Works out the pay rows and the total cost range for a saved crew, ready to show on the page.
def crew_estimate(crew):
    # Each specialty works a range of days, so each cost is a low-high range.
    rows = []
    total_workers = 0
    total_hourly = 0
    total_low = 0
    total_high = 0
    for member in crew["members"]:
        if member["role"] not in CREW_RATES:
            # a specialty that was removed from CREW_RATES after this crew was saved
            continue
        specialty = CREW_RATES[member["role"]]
        hourly = member["workers"] * specialty["rate"]
        low = hourly * HOURS_PER_DAY * member["days"][0]
        high = hourly * HOURS_PER_DAY * member["days"][1]
        rows.append({
            "name": specialty["name"],
            "workers": member["workers"],
            "rate": money(specialty["rate"]),
            "hourly": money(hourly),
            "days": show_range(member["days"][0], member["days"][1], after=" days"),
            "cost": show_range(round_cost(low, crew), round_cost(high, crew), before="$"),
        })
        total_workers = total_workers + member["workers"]
        total_hourly = total_hourly + hourly
        total_low = total_low + low
        total_high = total_high + high

    return {
        "label": crew["label"],
        "rows": rows,
        "workers": total_workers,
        "hourly": money(total_hourly),
        "days": show_range(crew["days"][0], crew["days"][1], after=" working days"),
        "cost": show_range(round_cost(total_low, crew), round_cost(total_high, crew), before="$"),
    }
