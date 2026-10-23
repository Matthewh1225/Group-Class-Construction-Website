const pageData = JSON.parse(document.getElementById("crew-data").textContent);
const form = document.getElementById("crew-form");
const labelInput = document.getElementById("crew-label");
const projectMin = document.getElementById("project-days-min");
const projectMax = document.getElementById("project-days-max");
const rows = form.querySelectorAll("[data-role]");
const error = document.getElementById("crew-error");
const saveButton = document.getElementById("save-crew");
const cartButton = document.getElementById("add-crew-to-cart");
const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

function costText(low, high) {
    if (low === high) {
        return currency.format(low);
    }
    return currency.format(low) + " – " + currency.format(high);
}

function calculateCrew(crew) {
    const result = { workers: 0, hourly: 0, low: 0, high: 0, costs: {} };
    for (const member of crew.members) {
        const hourly = member.workers * pageData.rates[member.role].rate;
        const low = hourly * pageData.hoursPerDay * member.days[0];
        const high = hourly * pageData.hoursPerDay * member.days[1];
        result.workers += member.workers;
        result.hourly += hourly;
        result.low += low;
        result.high += high;
        result.costs[member.role] = costText(low, high);
    }
    return result;
}

function updateEstimate() {
    labelInput.setCustomValidity("");
    if (labelInput.value.trim() === "") {
        labelInput.setCustomValidity("Enter a crew name.");
    }
    projectMax.setCustomValidity("");
    if (projectMax.valueAsNumber < projectMin.valueAsNumber) {
        projectMax.setCustomValidity("Maximum days must be at least minimum days.");
    }
    const selected = {
        label: labelInput.value,
        days: [projectMin.valueAsNumber, projectMax.valueAsNumber],
        members: [],
    };
    for (const row of rows) {
        const input = row.querySelector('[data-field="workers"]');
        const workers = input.valueAsNumber;
        row.querySelector('[data-worker-step="-1"]').disabled = workers <= Number(input.min);
        row.querySelector('[data-worker-step="1"]').disabled = workers >= Number(input.max);
        row.classList.toggle("in-crew", workers > 0);
        if (workers > 0) {
            selected.members.push({role: row.dataset.role, workers: workers, days: selected.days});
        }
    }
    const valid = form.checkValidity();
    const hasWorkers = selected.members.length > 0;
    if (valid) {
        const result = calculateCrew(selected);
        for (const row of rows) {
            row.querySelector("[data-cost]").textContent = result.costs[row.dataset.role] || currency.format(0);
        }
        document.getElementById("total-cost").textContent = costText(result.low, result.high);
        document.getElementById("total-workers").textContent = result.workers;
        document.getElementById("total-hourly").textContent = currency.format(result.hourly);
        document.getElementById("crew-input").value = JSON.stringify(selected);
    } else {
        for (const row of rows) {
            row.querySelector("[data-cost]").textContent = "—";
        }
        document.getElementById("total-cost").textContent = "—";
        document.getElementById("total-workers").textContent = "—";
        document.getElementById("total-hourly").textContent = "—";
        document.getElementById("crew-input").value = "";
    }
    error.textContent = "";
    if (!valid) {
        error.textContent = "Enter valid worker counts and a project duration range.";
    } else if (!hasWorkers) {
        error.textContent = "Add at least one worker to save a crew.";
    }
    error.hidden = error.textContent === "";
    if (saveButton) {
        saveButton.disabled = !valid || !hasWorkers;
    }
    cartButton.disabled = !valid || !hasWorkers;
    return valid && hasWorkers;
}

const saved = pageData.savedCrew;
if (saved) {
    labelInput.value = saved.label;
    projectMin.value = saved.days[0];
    projectMax.value = saved.days[1];
    for (const member of saved.members) {
        const row = form.querySelector('[data-role="' + member.role + '"]');
        row.querySelector('[data-field="workers"]').value = member.workers;
    }
}

form.addEventListener("input", updateEstimate);

form.addEventListener("click", function (event) {
    const button = event.target.closest("[data-worker-step]");
    if (!button) return;
    const input = button.closest("[data-role]").querySelector('[data-field="workers"]');
    input.stepUp(Number(button.dataset.workerStep));
    input.dispatchEvent(new Event("input", { bubbles: true }));
});

form.addEventListener("submit", function (event) {
    if (!updateEstimate()) {
        event.preventDefault();
        form.reportValidity();
        return;
    }
    if (event.submitter) event.submitter.disabled = true;
});

// Restore the save button when Back returns to this page.
window.addEventListener("pageshow", updateEstimate);
updateEstimate();
