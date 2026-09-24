const plannerForms = document.querySelectorAll(".planner-container form, .planner-step form");

plannerForms.forEach(function (form) {
    form.addEventListener("submit", function (event) {
        const mode = form.querySelector('[name="projectMode"]')?.value;
        const size = form.querySelector('[name="projectSize"]')?.value;
        const isreviewing = form.querySelector('[name="plannerAction"]');
        const reviewMode = mode === "custom" && ["large", "mega"].includes(size);
        const chosePro = event.submitter?.value === "pro";
        const status = form.querySelector(".plan-status");

        if (isreviewing) {
            status.textContent = "reviewing and updating your materials list...";
        } else if (reviewMode || chosePro) {
            status.textContent = "reviewing your project and checking for missing details...";
        } else {
            status.textContent = "Generating your materials list...";
        }

        status.hidden = false;
    });
});

window.addEventListener("pageshow", function () {
    plannerForms.forEach(function (form) {
        form.querySelector(".plan-status").hidden = true;
    });
});
