export async function submitAccountForm(form, message, data) {
    try {
        const response = await fetch(form.action, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(data),
        });
        const result = await response.json();

        if (response.ok) {
            window.location.href = result.redirect_url;
        } else {
            message.textContent = result.error || "Unable to submit the form.";
        }
    } catch {
        message.textContent = "Unable to contact the server.";
    }
    const passwordFields = form.querySelectorAll('input[type="password"]');
    for (const input of passwordFields) {
        input.value = "";
    }
}
