import {setupPasswordToggles, submitAccountForm} from "./account-forms.js";

const loginForm = document.getElementById("login-form");
const message = document.getElementById("login-message");

setupPasswordToggles(loginForm);

loginForm.addEventListener("submit", function (event) {
    event.preventDefault();
    message.textContent = "";
    const data = Object.fromEntries(new FormData(loginForm));
    data.email = data.email.trim();
    submitAccountForm(loginForm, message, data);
});
