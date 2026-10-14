# Simple AI planner

All tiers return the same estimate JSON. Only the models, reasoning levels and
number of estimates differ.

| Tier | Interpret | Estimate | Review |
| --- | --- | --- | --- |
| Fast | Gemini Low | GPT-OSS Low | Gemini Low |
| Standard | Gemini Medium | GPT-OSS High | Gemini Medium |
| Pro | Gemini High | Gemini High and GPT-OSS High in parallel | Nemotron High |

The interpreter returns a short summary, a list of project details and any
essential questions. Questions pause the job until answered. Original user input
and answers are also sent directly to the planners and reviewer.

Fast and Standard create one estimate and review it. Pro creates two independent
estimates from the same inputs, then reconciles them. The reviewer returns a
complete corrected estimate using exactly the same schema as the planners.
There are no requirement IDs, scope links, finding ledgers or correction rounds.
If a provider returns invalid JSON or calculation inputs, it gets one bounded
recovery attempt. Pro can use Gemini High as a fallback reviewer; that result is
marked partial with a visible warning.

## Shared estimate JSON

```json
{
  "summary": "Floor a 10 ft by 12 ft room",
  "materials": [{
    "name": "Vinyl flooring",
    "specification": "Click-lock with attached underlayment",
    "quantity": 132,
    "unit": "sq_ft",
    "waste_percent": 10,
    "round_up": false,
    "calculation": {
      "method": "rectangle_area",
      "inputs": [
        {"name": "length", "value": 10, "unit": "ft"},
        {"name": "width", "value": 12, "unit": "ft"},
        {"name": "layers", "value": 1, "unit": "count"}
      ]
    },
    "notes": "One layer; 10% allowance for cuts."
  }],
  "assumptions": ["Existing subfloor is ready"],
  "questions": [],
  "warnings": []
}
```

`contracts.py` uses small Pydantic models to check required fields, types, allowed
methods and numeric ranges. The same models generate the provider JSON schema.
Python recomputes area, wall area, perimeter, coverage and count quantities from
explicit inputs, converting units and applying waste and rounding once. This
happens before each estimate is saved or sent to the reviewer, including Pro's
reconciled result. Rechecking an estimate does not double its waste allowance.

`quantity` always means the final estimated amount. Unsupported methods use
`manual` with no inputs and explanatory notes. Their quantities already include
any stated waste/rounding and are labeled unverified. Unknown quantities use null.
Questions pause for user input; unknown quantities, review warnings or fallback
review produce a partial result. Python checks arithmetic, not whether the AI
selected the right measurements or materials; that is the reviewer's role.

The saved result wraps the estimate with tier/status and Pro's independent
estimates. Catalog products, purchase packaging and prices are not implemented.

## Running and testing

Run the server and worker in separate terminals:

```powershell
.\.venv\Scripts\python.exe app.py
.\.venv\Scripts\python.exe -m planning.worker
```

Both use `PLANNER_JOB_DATABASE` (default `instance/planner_jobs.sqlite3`). Restart
both after configuration changes. Successful stages survive retries and worker
restarts. Daily new-job limits and per-job provider attempt limits remain in force.

- Gemini 3.5 Flash Lite remains the intentional testing override for 3.8.
- `PLANNER_PRO_TEST_ACCESS=true` enables Pro for all signed-in testing users.
  Disable it to restore the comma-separated `PLANNER_PRO_USER_IDS` allowlist.
- Workflow version 5 uses this simplified format. Older saved results still render;
  unfinished jobs using the old format must be started as new projects.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tests/live_planner_check.py --tier pro --scenario drywall
```

Live checks use real providers, a fixture login and an isolated temporary queue.
Reports are saved under `instance/verification`. Tiers: fast, standard, pro.
Scenarios: flooring, painting, drywall.
