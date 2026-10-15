const plannerForms = document.querySelectorAll(".planner-container form, .planner-step form");

plannerForms.forEach(function (form) {
    form.addEventListener("submit", function (event) {
        const status = form.querySelector(".plan-status");
        status.textContent = "Saving your project and starting planning...";
        status.hidden = false;
    });
});

// pageshow also runs when the browser restores a page with the back button
window.addEventListener("pageshow", function () {
    plannerForms.forEach(function (form) {
        form.querySelector(".plan-status").hidden = true;
    });
});
