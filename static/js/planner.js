const methodStep = document.getElementById("method-step");
const templateStep = document.getElementById("template-step");
const sizeStep = document.getElementById("size-step");
const plannerStep = document.getElementById("planner-form");
const steps = document.querySelectorAll(".planner-step, .planner-container");
const sizeInput = document.getElementById("project-size");
const progressSteps = document.querySelectorAll(".planner-progress li");

function showProgress(stage) {
    for (const item of progressSteps) {
        if (item.dataset.stage === stage) {
            item.setAttribute("aria-current", "step");
        } else {
            item.removeAttribute("aria-current");
        }
    }
}

function showStep(selectedStep) {
    for (const step of steps) {
        step.hidden = step !== selectedStep;
    }
    const hasDetails = selectedStep === plannerStep || selectedStep.classList.contains("template-questions");
    if (hasDetails) {
        showProgress("details");
    } else {
        showProgress("project");
    }
    const heading = selectedStep.querySelector("h2") || selectedStep.querySelector("button");
    if (heading) heading.focus({ preventScroll: true });
    document.querySelector(".planner-progress").scrollIntoView({ block: "nearest" });
}

document.getElementById("choose-template").addEventListener("click", function () {
    showStep(templateStep);
});

document.getElementById("choose-custom").addEventListener("click", function () {
    showStep(sizeStep);
});

for (const button of document.querySelectorAll(".project-option")) {
    button.addEventListener("click", function () {
        sizeInput.value = button.dataset.size;
        showStep(plannerStep);
    });
}

for (const button of document.querySelectorAll(".template-option")) {
    button.addEventListener("click", function () {
        showStep(document.getElementById(`${button.dataset.template}-questions-step`));
    });
}

for (const button of document.querySelectorAll(".template-back")) {
    button.addEventListener("click", function () {
        showStep(templateStep);
    });
}

for (const button of document.querySelectorAll(".back-button")) {
    button.addEventListener("click", function () {
        sizeInput.value = "";
        showStep(methodStep);
    });
}

document.querySelector(".details-back").addEventListener("click", function () {
    showStep(sizeStep);
});

// Custom and template forms share the AI mode and Generate controls.
const plannerForms = document.querySelectorAll(".planner-page form");

for (const form of plannerForms) {
    form.addEventListener("focusin", function (event) {
        if (event.target.closest(".planner-tiers, .planner-generate")) {
            showProgress("estimate");
        } else {
            showProgress("details");
        }
    });

    // The server also checks the key to stop duplicate submissions.
    form.addEventListener("submit", function () {
        const status = form.querySelector(".plan-status");
        const button = form.querySelector(".planner-generate");
        status.textContent = "Starting planning...";
        status.hidden = false;
        button.disabled = true;
        button.classList.add("is-busy");
    });
}

// Re-enable buttons when the Back button restores this page.
window.addEventListener("pageshow", function () {
    for (const form of plannerForms) {
        const button = form.querySelector(".planner-generate");
        form.querySelector(".plan-status").hidden = true;
        button.disabled = false;
        button.classList.remove("is-busy");
    }
});
