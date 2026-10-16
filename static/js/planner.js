import "./planner-submit.js";

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
    // Move keyboard users to the heading of the step that just appeared.
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

document.querySelectorAll(".planner-page form").forEach(function (form) {
    form.addEventListener("focusin", function (event) {
        showProgress(event.target.closest(".planner-tiers, .planner-generate") ? "estimate" : "details");
    });
});
