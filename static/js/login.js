import {submitAccountForm} from "./authaccount.js";

const loginForm = document.getElementById("login-form");
const message = document.getElementById("login-message");

loginForm.addEventListener("submit", function (event) {
    event.preventDefault();
    message.textContent = "";
    const data = Object.fromEntries(new FormData(loginForm));
    data.username = data.username.trim();
    if (!data.username || !data.password) {
        message.textContent = "Please enter both username and password.";
        return;
    }
    submitAccountForm(loginForm, message, data);
});
