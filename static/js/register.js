import {submitAccountForm} from "./authaccount.js";

const registerForm = document.getElementById("register-form");
const message = document.getElementById("register-message");

registerForm.addEventListener("submit", function (event) {
    event.preventDefault();
    message.textContent = "";

    const data = Object.fromEntries(new FormData(registerForm));
    if (data.password !== data.confirm_password) {
        message.textContent = "Passwords do not match.";
        return;
    }
    submitAccountForm(registerForm, message, data);
});
