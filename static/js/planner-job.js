const jobPage = document.getElementById("planning-job");
const progress = document.getElementById("job-progress");
let failures = 0;

async function updateJob() {
    if (!["queued", "running"].includes(jobPage.dataset.jobStatus)) {
        return;
    }
    try {
        const response = await fetch(jobPage.dataset.statusUrl, { cache: "no-store" });
        if (!response.ok) {
            throw new Error("Progress is unavailable.");
        }
        const job = await response.json();
        failures = 0;
        progress.textContent = job.status === "queued" ? "Waiting to start" : job.phase;
        if (!["queued", "running"].includes(job.status)) {
            window.location.reload();
            return;
        }
        window.setTimeout(updateJob, 2000);
    } catch (error) {
        failures += 1;
        if (failures < 3) {
            window.setTimeout(updateJob, 4000);
        } else {
            progress.textContent = "Progress is temporarily unavailable. Refresh this page to try again.";
        }
    }
}

if (jobPage) {
    window.setTimeout(updateJob, 2000);
}

// Long estimates are searchable; all materials remain visible without JavaScript.
const materialRows = [...document.querySelectorAll("[data-material-row]")];
const materialSearch = document.getElementById("material-search");
if (materialSearch && materialRows.length > 8) {
    document.getElementById("material-filter").hidden = false;
    materialSearch.addEventListener("input", () => {
        const query = materialSearch.value.trim().toLowerCase();
        let visible = 0;
        for (const row of materialRows) {
            row.hidden = !row.textContent.toLowerCase().includes(query);
            if (!row.hidden) visible += 1;
        }
        document.getElementById("material-search-status").textContent =
            `${visible} of ${materialRows.length} materials shown`;
    });
}
