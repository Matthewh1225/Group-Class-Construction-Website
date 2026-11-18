import { setupPasswordToggles } from "./account-forms.js";

const accountForm = document.getElementById("account-form");
const editButton = document.getElementById("account-edit");
const cancelLink = document.getElementById("account-cancel");
const accountFields = document.getElementById("account-fields");
const accountActions = document.getElementById("account-actions");
const accountHasError = accountForm.dataset.hasError === "true";

function setEditing(editing) {
    accountFields.disabled = !editing;
    accountActions.hidden = !editing;
    editButton.hidden = editing;
}

editButton.addEventListener("click", function () {
    setEditing(true);
    document.getElementById("account-first-name").focus();
});

cancelLink.addEventListener("click", function (event) {
    // Reload saved values after an error.
    if (accountHasError) {
        return;
    }
    event.preventDefault();
    accountForm.reset();
    setEditing(false);
    editButton.focus();
});

setEditing(accountHasError);


const passwordForm = document.getElementById("password-form");
const openPasswordButton = document.getElementById("password-open");
const cancelPasswordButton = document.getElementById("password-cancel");
const newPassword = document.getElementById("new-password");
const confirmPassword = document.getElementById("confirm-password");

function setPasswordFormOpen(open) {
    passwordForm.hidden = !open;
    openPasswordButton.hidden = open;
}

openPasswordButton.addEventListener("click", function () {
    setPasswordFormOpen(true);
    document.getElementById("current-password").focus();
});

cancelPasswordButton.hidden = false;
cancelPasswordButton.addEventListener("click", function () {
    passwordForm.reset();
    setPasswordFormOpen(false);
    openPasswordButton.focus();
});

function checkNewPasswords() {
    if (newPassword.value && !/[0-9]/.test(newPassword.value)) {
        newPassword.setCustomValidity("Include at least one number.");
    } else {
        newPassword.setCustomValidity("");
    }
    if (confirmPassword.value && confirmPassword.value !== newPassword.value) {
        confirmPassword.setCustomValidity("The new passwords do not match.");
    } else {
        confirmPassword.setCustomValidity("");
    }
}
newPassword.addEventListener("input", checkNewPasswords);
confirmPassword.addEventListener("input", checkNewPasswords);

setupPasswordToggles(passwordForm);
setPasswordFormOpen(passwordForm.dataset.hasError === "true");
