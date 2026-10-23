import {passwordChecks, setupGoogleSignIn, setupPasswordToggles, submitAccountForm} from "./account-forms.js";

const registerForm = document.getElementById("register-form");
const message = document.getElementById("register-message");
const password = document.getElementById("password");
const confirmPassword = document.getElementById("confirm_password");
const matchMessage = document.getElementById("match-message");

function checkPasswordRules() {
    const checks = passwordChecks(password.value);
    document.querySelector('[data-rule="length"]').classList.toggle("is-met", checks.length);
    document.querySelector('[data-rule="number"]').classList.toggle("is-met", checks.number);
    return checks.length && checks.number;
}

// Wait until the user starts confirming the password to show a mismatch.
function checkMatch() {
    const matches = password.value === confirmPassword.value;
    if (confirmPassword.value === "" || matches) {
        matchMessage.textContent = "";
    } else {
        matchMessage.textContent = "Passwords do not match.";
    }
    return matches;
}

setupPasswordToggles(registerForm);
setupGoogleSignIn(message);
password.addEventListener("input", function () {
    checkPasswordRules();
    checkMatch();
});
confirmPassword.addEventListener("input", checkMatch);

registerForm.addEventListener("submit", function (event) {
    event.preventDefault();
    message.textContent = "";

    if (!checkPasswordRules()) {
        message.textContent = "Your password needs every item on the checklist.";
        password.focus();
        return;
    }
    if (!checkMatch()) {
        confirmPassword.focus();
        return;
    }

    const data = {
        firstName: registerForm.elements.firstName.value,
        lastName: registerForm.elements.lastName.value,
        email: registerForm.elements.email.value,
        password: password.value,
        confirm_password: confirmPassword.value,
    };
    submitAccountForm(registerForm, message, data);
});
