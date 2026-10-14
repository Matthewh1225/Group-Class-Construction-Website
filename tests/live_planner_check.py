"""Opt-in live checks: python tests/live_planner_check.py --tier fast.

Uses real providers and a real worker subprocess, but a fixture login and an
isolated temporary queue. It never creates a production account or saved plan.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import app
from planning.ai_config import WORKFLOW_TIERS
from planning.jobs import get_job
from utils.rate_limits import limiter


SCENARIOS = {
    "flooring": {
        "request": "Supply click-lock vinyl flooring with an attached underlayment for a 10 ft by 12 ft rectangular room floor. One layer; 10 percent cutting waste for flooring only. Existing subfloor is ready. No glue, separate underlayment, trims or transitions are needed. Exclude tools. Do not invent product packaging or prices.",
        "unit": "sq_ft", "expected": 132,
    },
    "painting": {
        "request": "Paint a flat 400 sq_ft interior wall surface with two coats. Paint coverage is supplied by the user: 400 sq_ft/gallon per coat. Zero paint waste for this estimate. Include 80 ft of painter tape for the measured wall edges, zero tape waste, and surface preparation consumables with explicit estimates. No openings or repairs. Exclude tools.",
        "unit": "gallon", "expected": 2,
    },
    "drywall": {
        "request": "Cover one straight 32 ft long by 8 ft tall interior wall face with one layer of 4 ft by 8 ft drywall, 32 sq_ft/sheet. No openings. Zero waste: eight full sheets fit with no cuts. Include screws, joint tape and joint compound with explicit quantity assumptions. Existing framing is suitable. Exclude paint and tools.",
        "unit": "sheet", "expected": 8,
    },
}


def check(tier, name):
    scenario = SCENARIOS[name]
    with tempfile.TemporaryDirectory() as folder:
        previous_enabled = WORKFLOW_TIERS[tier]["enabled"]
        if tier in {"standard", "pro"}:
            # Exercise this tier only in the isolated test application.
            WORKFLOW_TIERS[tier]["enabled"] = True
        previous_entitlement = os.environ.get("PLANNER_PRO_USER_IDS")
        if tier == "pro":
            os.environ["PLANNER_PRO_USER_IDS"] = "123456789"
        previous_path = os.environ.get("PLANNER_JOB_DATABASE")
        os.environ["PLANNER_JOB_DATABASE"] = str(Path(folder) / "live_jobs.sqlite3")
        try:
            app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
            limiter.enabled = False
            client = app.test_client()
            with client.session_transaction() as session:
                session["user_id"] = 123456789
                session["planner_token"] = "live-test-only-token"
            started = time.monotonic()
            response = client.post("/planner/jobs", data={
                "projectMode": "custom", "projectSize": "small", "userInput": scenario["request"],
                "plannerToken": "live-test-only-token", "submissionKey": "live-test-" + name,
                "planType": tier,
            })
            if response.status_code != 303:
                return {"tier": tier, "scenario": name, "submission_status": response.status_code, "passed": False}
            job_id = response.location.rsplit("/", 1)[-1]
            subprocess.run([sys.executable, "-m", "planning.worker", "--once"], cwd=ROOT, check=True, capture_output=True, timeout=2000)
            job = get_job(job_id, 123456789)
            record = {"tier": tier, "scenario": name, "status": job["status"], "error": job["error"],
                      "seconds": round(time.monotonic() - started, 2), "calls": len(job["attempts"]),
                      "page_status": client.get(response.location).status_code,
                      "tokens": sum(attempt.get("metadata", {}).get("total_tokens") or 0 for attempt in job["attempts"]),
                      "fixture_login": True, "live_providers": True, "worker_subprocess": True,
                      "fixture_entitlement": tier == "pro",
                      "attempts": job["attempts"], "specification": job.get("specification"), "result": job["result"]}
            record["original_request"] = scenario["request"]
            matched = False
            if job["result"]:
                for material in job["result"]["estimate"]["materials"]:
                    if material["unit"] in {scenario["unit"], scenario["unit"] + "s"}:
                        quantity = material["quantity"]
                        if quantity is not None and abs(quantity - scenario["expected"]) < 0.0001:
                            matched = True
                record["audited_final_version"] = job["result"]["audited"]
            record["expected_quantity"] = scenario["expected"]
            record["primary_quantity_matched"] = matched
            record["passed"] = job["status"] == "complete" and matched and record.get("audited_final_version", False)
            return record
        finally:
            WORKFLOW_TIERS[tier]["enabled"] = previous_enabled
            if previous_entitlement is None:
                os.environ.pop("PLANNER_PRO_USER_IDS", None)
            else:
                os.environ["PLANNER_PRO_USER_IDS"] = previous_entitlement
            if previous_path is None:
                os.environ.pop("PLANNER_JOB_DATABASE", None)
            else:
                os.environ["PLANNER_JOB_DATABASE"] = previous_path


def main():
    parser = argparse.ArgumentParser(description="Run opt-in live planner checks (uses provider quota).")
    parser.add_argument("--tier", choices=["fast", "standard", "pro"], default="fast")
    parser.add_argument("--scenario", choices=list(SCENARIOS), default="flooring")
    options = parser.parse_args()
    record = check(options.tier, options.scenario)
    output = ROOT / "instance" / "verification"
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{options.tier}_{options.scenario}_{time.time_ns()}.json"
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    summary = record.copy()
    for key in ["result", "attempts", "specification"]:
        summary.pop(key, None)
    summary.pop("original_request", None)
    summary["report"] = str(path)
    print(json.dumps(summary))
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
