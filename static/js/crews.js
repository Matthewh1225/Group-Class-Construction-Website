const pageData = JSON.parse(document.getElementById("crew-data").textContent);
const form = document.getElementById("crew-form");
const labelInput = document.getElementById("crew-label");
const projectMin = document.getElementById("project-days-min");
const projectMax = document.getElementById("project-days-max");
const rows = Array.from(form.querySelectorAll("[data-role]"));
const error = document.getElementById("crew-error");
const saveButton = document.getElementById("save-crew");
const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

const saved = pageData.savedCrew;
const crew = {
    label: saved ? saved.label : "Custom crew",
    days: saved ? [...saved.days] : [1, 1],
    members: Object.keys(pageData.rates).map(function (role) {
        const member = saved && saved.members.find((item) => item.role === role);
        return { role: role, workers: member ? member.workers : 0, days: saved ? [...saved.days] : [1, 1] };
    }),
};

function costText(low, high) {
    return low === high ? currency.format(low) : currency.format(low) + " – " + currency.format(high);
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
    labelInput.setCustomValidity(crew.label.trim() ? "" : "Enter a crew name.");
    projectMax.setCustomValidity(crew.days[1] < crew.days[0] ? "Maximum days must be at least minimum days." : "");
    for (const row of rows) {
        const member = crew.members.find((item) => item.role === row.dataset.role);
        const workers = row.querySelector('[data-field="workers"]');
        row.querySelector('[data-worker-step="-1"]').disabled = member.workers <= Number(workers.min);
        row.querySelector('[data-worker-step="1"]').disabled = member.workers >= Number(workers.max);
        row.classList.toggle("in-crew", member.workers > 0);
    }
    const valid = form.checkValidity();
    const selected = { label: crew.label, days: crew.days, members: [] };
    for (const member of crew.members) {
        if (member.workers > 0) {
            selected.members.push({ role: member.role, workers: member.workers, days: [...member.days] });
        }
    }
    const result = valid ? calculateCrew(selected) : null;
    for (const row of rows) {
        row.querySelector("[data-cost]").textContent = result ? result.costs[row.dataset.role] || currency.format(0) : "—";
    }
    document.getElementById("total-cost").textContent = result ? costText(result.low, result.high) : "—";
    document.getElementById("total-workers").textContent = result ? result.workers : "—";
    document.getElementById("total-hourly").textContent = result ? currency.format(result.hourly) : "—";
    error.textContent = !valid ? "Enter valid worker counts and a project duration range." : selected.members.length === 0 ? "Add at least one worker to save a crew." : "";
    error.hidden = error.textContent === "";
    if (saveButton) saveButton.disabled = !valid || selected.members.length === 0;
    document.getElementById("crew-input").value = valid ? JSON.stringify(selected) : "";
    return valid && selected.members.length > 0;
}

labelInput.value = crew.label;
projectMin.value = crew.days[0];
projectMax.value = crew.days[1];
for (const row of rows) {
    const member = crew.members.find((item) => item.role === row.dataset.role);
    row.querySelector('[data-field="workers"]').value = member.workers;
}

form.addEventListener("input", function (event) {
    const input = event.target;
    const row = input.closest("[data-role]");
    if (row) {
        const member = crew.members.find((item) => item.role === row.dataset.role);
        member.workers = row.querySelector('[data-field="workers"]').valueAsNumber;
    } else {
        crew.label = labelInput.value;
        crew.days = [projectMin.valueAsNumber, projectMax.valueAsNumber];
        for (const member of crew.members) member.days = [...crew.days];
    }
    updateEstimate();
});

form.addEventListener("click", function (event) {
    const button = event.target.closest("[data-worker-step]");
    if (!button) return;
    const input = button.closest("[data-role]").querySelector('[data-field="workers"]');
    input.stepUp(Number(button.dataset.workerStep));
    input.dispatchEvent(new Event("input", { bubbles: true }));
});

form.addEventListener("submit", function (event) {
    if (!updateEstimate() || !saveButton) {
        event.preventDefault();
        form.reportValidity();
        return;
    }
    saveButton.disabled = true;
});

// Restore the save button when Back returns to this page.
window.addEventListener("pageshow", updateEstimate);
updateEstimate();
