import {submitAccountForm} from "./account-forms.js";

const loginForm = document.getElementById("login-form");
const message = document.getElementById("login-message");

loginForm.addEventListener("submit", function (event) {
    // stop the normal page reload so JS can send the form
    event.preventDefault();
    message.textContent = "";
    // turn the form's name/value pairs into a plain object
    const data = Object.fromEntries(new FormData(loginForm));
    data.username = data.username.trim();
    submitAccountForm(loginForm, message, data);
});
