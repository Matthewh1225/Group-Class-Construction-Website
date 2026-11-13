import {setupGoogleSignIn, setupPasswordToggles, submitAccountForm} from "./account-forms.js";

const loginForm = document.getElementById("login-form");
const message = document.getElementById("login-message");

// Clear form values restored by the browser.
window.addEventListener("pageshow", function () {
    loginForm.reset();
});

// Keep the password readonly until focus to avoid autofill.
const passwordInput = loginForm.elements.password;
function unlockPassword() {
    passwordInput.removeAttribute("readonly");
}
passwordInput.addEventListener("focus", unlockPassword);
passwordInput.addEventListener("pointerdown", unlockPassword);

setupPasswordToggles(loginForm);
setupGoogleSignIn(message);

loginForm.addEventListener("submit", function (event) {
    event.preventDefault();
    message.textContent = "";
    const data = {
        email: loginForm.elements.email.value.trim(),
        password: loginForm.elements.password.value,
    };
    submitAccountForm(loginForm, message, data);
});
