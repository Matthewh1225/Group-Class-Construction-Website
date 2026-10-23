import {setupGoogleSignIn, setupPasswordToggles, submitAccountForm} from "./account-forms.js";

const loginForm = document.getElementById("login-form");
const message = document.getElementById("login-message");

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
