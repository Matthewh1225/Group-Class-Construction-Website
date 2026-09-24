
import "./plannersubmit.js";

const methodStep = document.getElementById("method-step");
const templateStep = document.getElementById("template-step");
const sizeStep = document.getElementById("size-step");
const plannerStep = document.getElementById("planner-form");
const plannerResult = document.getElementById("planner-result");
const responseOutput = plannerResult.querySelector("textarea");
const templateQuestionSteps = document.querySelectorAll(".template-questions");
const steps = [methodStep, templateStep, sizeStep, plannerStep, ...templateQuestionSteps];
const modeInput = document.getElementById("project-mode");
const sizeInput = document.getElementById("project-size");
const templateInput = document.getElementById("project-template");
const descriptionInput = document.getElementById("user-input");

function showStep(selectedStep) {
    for (const step of steps) {
        step.hidden = step !== selectedStep;
    }

    plannerResult.hidden = true;
    responseOutput.value = "";
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
        descriptionInput.value = "";
        showStep(methodStep);
    });
});
