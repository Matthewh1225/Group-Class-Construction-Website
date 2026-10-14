const plannerForms = document.querySelectorAll(".planner-container form, .planner-step form");

plannerForms.forEach(function (form) {
    form.addEventListener("submit", function (event) {
        // ?. gives undefined if this form does not have the input
        const reviewInput = form.querySelector('[name="plannerAction"]');
        const status = form.querySelector(".plan-status");

        if (reviewInput) {
            status.textContent = "reviewing and updating your materials list...";
        } else {
            status.textContent = "Saving your project and starting planning...";
        }

        status.hidden = false;
    });
});

// pageshow also runs when the browser restores a page with the back button
window.addEventListener("pageshow", function () {
    plannerForms.forEach(function (form) {
        form.querySelector(".plan-status").hidden = true;
    });
});
