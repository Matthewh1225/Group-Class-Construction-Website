const jobPage = document.getElementById("planning-job");
const progress = document.getElementById("job-progress");
let failures = 0;

async function updateJob() {
    try {
        const response = await fetch(jobPage.dataset.statusUrl, { cache: "no-store" });
        if (!response.ok) {
            throw new Error("Progress is unavailable.");
        }
        const job = await response.json();
        failures = 0;
        if (job.status !== "queued" && job.status !== "running") {
            window.location.reload();
            return;
        }
        if (job.status === "queued") {
            progress.textContent = "Queued for planning";
        } else {
            progress.textContent = job.phase;
        }
        window.setTimeout(updateJob, 2000);
    } catch {
        // Retry twice, 4 seconds apart.
        failures += 1;
        if (failures < 3) {
            window.setTimeout(updateJob, 4000);
        } else {
            progress.textContent = "Progress unavailable. Refresh to try again.";
        }
    }
}

const startingStatus = jobPage.dataset.jobStatus;
if (startingStatus === "queued" || startingStatus === "running") {
    window.setTimeout(updateJob, 2000);
}

const submitOnceForms = document.querySelectorAll("form[data-submit-once]");
for (const form of submitOnceForms) {
    form.addEventListener("submit", function () {
        form.querySelector("button[type=submit]").disabled = true;
    });
}

// Re-enable buttons when the Back button restores this page.
window.addEventListener("pageshow", function () {
    for (const form of submitOnceForms) {
        form.querySelector("button[type=submit]").disabled = false;
    }
});

// Keep all material rows visible until JavaScript is ready.
const materialRows = document.querySelectorAll("[data-material-row]");
const materialSearch = document.getElementById("material-search");
if (materialSearch !== null && materialRows.length > 8) {
    document.getElementById("material-filter").hidden = false;
    materialSearch.addEventListener("input", function () {
        const query = materialSearch.value.trim().toLowerCase();
        let visible = 0;
        for (const row of materialRows) {
            row.hidden = !row.textContent.toLowerCase().includes(query);
            if (!row.hidden) {
                visible += 1;
            }
        }
        document.getElementById("material-search-status").textContent =
            `${visible} of ${materialRows.length} materials shown`;
    });
}
