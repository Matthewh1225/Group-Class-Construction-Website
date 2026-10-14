// This previews the future project-delete flow. The confirm action stays disabled.
const deleteDialog = document.getElementById("delete-project-dialog");
if (deleteDialog) {
    document.querySelectorAll(".dashboard-delete-trigger").forEach(function (button) {
        button.addEventListener("click", function () {
            document.getElementById("delete-project-name").textContent = button.dataset.projectName || "This project";
            deleteDialog.showModal();
        });
    });
    deleteDialog.querySelector("[data-close-dialog]").addEventListener("click", function () {
        deleteDialog.close();
    });
}

// Keep local validation ready for the account forms.
document.querySelectorAll(".dashboard-form").forEach(function (form) {
    form.addEventListener("submit", function (event) {
        event.preventDefault();
        const message = form.querySelector(".dashboard-form-message");
        delete message.dataset.error;
        if (!form.reportValidity()) return;

        if (form.id === "password-form") {
            const password = form.querySelector('[name="new_password"]');
            const confirmation = form.querySelector('[name="confirm_new_password"]');
            if (password.value !== confirmation.value) {
                message.textContent = "New passwords do not match.";
                message.dataset.error = "true";
                confirmation.focus();
                return;
            }
        }
        message.textContent = "";
    });
    form.addEventListener("reset", function () {
        const message = form.querySelector(".dashboard-form-message");
        delete message.dataset.error;
        message.textContent = "";
    });
});
