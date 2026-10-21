const methodStep = document.getElementById("method-step");
const templateStep = document.getElementById("template-step");
const sizeStep = document.getElementById("size-step");
const plannerStep = document.getElementById("planner-form");
const templateQuestionSteps = document.querySelectorAll(".template-questions");
const steps = [methodStep, templateStep, sizeStep, plannerStep, ...templateQuestionSteps];
const modeInput = document.getElementById("project-mode");
const sizeInput = document.getElementById("project-size");
const templateInput = document.getElementById("project-template");
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
    showProgress(hasDetails ? "details" : "project");
    const heading = selectedStep.querySelector("h2") || selectedStep.querySelector("button");
    if (heading) heading.focus({ preventScroll: true });
    document.querySelector(".planner-progress").scrollIntoView({ block: "nearest" });
}

document.getElementById("choose-template").addEventListener("click", function () {
    modeInput.value = "template";
    showStep(templateStep);
});

document.getElementById("choose-custom").addEventListener("click", function () {
    modeInput.value = "custom";
    templateInput.value = "";
    showStep(sizeStep);
});

document.querySelectorAll(".project-option").forEach(function (button) {
    button.addEventListener("click", function () {
        sizeInput.value = button.dataset.size;
        templateInput.value = "";
        showStep(plannerStep);
    });
});

document.querySelectorAll(".template-option").forEach(function (button) {
    button.addEventListener("click", function () {
        const templateName = button.dataset.template;
        templateInput.value = templateName;
        sizeInput.value = button.dataset.size;
        showStep(document.getElementById(`${templateName}-questions-step`));
    });
});

document.querySelectorAll(".template-back").forEach(function (button) {
    button.addEventListener("click", function () {
        templateInput.value = "";
        sizeInput.value = "";
        showStep(templateStep);
    });
});

document.querySelectorAll(".back-button").forEach(function (button) {
    button.addEventListener("click", function () {
        modeInput.value = "";
        sizeInput.value = "";
        templateInput.value = "";
        showStep(methodStep);
    });
});

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
