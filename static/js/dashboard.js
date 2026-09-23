// need to confirm before deleting a user
document.querySelectorAll(".delete-user-form").forEach(function (form) {
    form.addEventListener("submit", function (event) {
        if (!window.confirm(`Delete ${form.dataset.username}? This cannot be undone.`)) {
            event.preventDefault();
        }
    });
});
