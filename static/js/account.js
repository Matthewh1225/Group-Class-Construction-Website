export async function submitAccountForm(form, message, data) {
    try {
        const response = await fetch(form.action, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(data),
        });
        const result = await response.json();

        if (result.redirect_url) {
            window.location.href = result.redirect_url;
        } else {
            message.textContent = result.error;
        }
    } catch {
        message.textContent = "Unable to contact the server.";
    }
    form.querySelectorAll('input[type="password"]').forEach(function (input) {
        input.value = "";
    });
}
