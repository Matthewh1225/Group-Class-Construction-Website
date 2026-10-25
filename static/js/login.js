import {setupGoogleSignIn, setupPasswordToggles, submitAccountForm} from "./account-forms.js";

const loginForm = document.getElementById("login-form");
const message = document.getElementById("login-message");

// Browsers restore form values on refresh and back/forward, so clear them.
window.addEventListener("pageshow", function () {
    loginForm.reset();
});

// The password starts readonly so it can't be autofilled; unlock it once the user clicks in.
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
