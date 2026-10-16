const plannerForms = document.querySelectorAll(".planner-container form, .planner-step form");

plannerForms.forEach(function (form) {
    form.addEventListener("submit", function () {
        const status = form.querySelector(".plan-status");
        const button = form.querySelector(".planner-generate");
        status.textContent = "Saving your project and starting planning...";
        status.hidden = false;
        button.disabled = true;
        button.classList.add("is-busy");
    });
});

// pageshow also runs when the browser restores a page with the back button
window.addEventListener("pageshow", function () {
    plannerForms.forEach(function (form) {
        form.querySelector(".plan-status").hidden = true;
        form.querySelector(".planner-generate").disabled = false;
        form.querySelector(".planner-generate").classList.remove("is-busy");
    });
});
