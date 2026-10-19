import {passwordChecks, setupPasswordToggles, submitAccountForm} from "./account-forms.js";

const registerForm = document.getElementById("register-form");
const message = document.getElementById("register-message");
const password = document.getElementById("password");
const confirmPassword = document.getElementById("confirm_password");
const matchMessage = document.getElementById("match-message");

function checkPasswordRules() {
    let allMet = true;
    const checks = passwordChecks(password.value, registerForm.dataset.passwordDigits);
    for (const [name, met] of Object.entries(checks)) {
        document.querySelector(`[data-rule="${name}"]`).classList.toggle("is-met", met);
        if (!met) allMet = false;
    }
    return allMet;
}

function checkMatch() {
    const matches = password.value === confirmPassword.value;
    // Avoid showing a mismatch before confirmation has been started.
    if (!confirmPassword.value) {
        matchMessage.textContent = "";
    } else {
        matchMessage.textContent = matches ? "" : "Passwords do not match.";
    }
    return matches;
}

setupPasswordToggles(registerForm);
password.addEventListener("input", function () {
    checkPasswordRules();
    checkMatch();
});
confirmPassword.addEventListener("input", checkMatch);

registerForm.addEventListener("submit", function (event) {
    event.preventDefault();
    message.textContent = "";

    const data = Object.fromEntries(new FormData(registerForm));
    if (!checkPasswordRules()) {
        message.textContent = "Your password needs every item on the checklist.";
        password.focus();
        return;
    }
    if (!checkMatch()) {
        confirmPassword.focus();
        return;
    }
    submitAccountForm(registerForm, message, data);
});
