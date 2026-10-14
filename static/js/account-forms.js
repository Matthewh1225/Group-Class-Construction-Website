export async function submitAccountForm(form, message, data) {
    if (form.dataset.submitting === "true") return;
    const submitButton = form.querySelector('button[type="submit"]');
    form.dataset.submitting = "true";
    form.setAttribute("aria-busy", "true");
    submitButton.disabled = true;
    try {
        const response = await fetch(form.action, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            // turn the form object into JSON for Flask
            body: JSON.stringify(data),
        });
        const result = await response.json();

        if (response.ok && result.redirect_url) {
            window.location.href = result.redirect_url;
        } else {
            message.textContent = result.error || "The request could not be completed.";
        }
    } catch {
        message.textContent = "Unable to contact the server.";
    } finally {
        // Clear secrets and release the form even when the request fails.
        form.querySelectorAll('input[type="password"]').forEach(function (input) {
            input.value = "";
        });
        delete form.dataset.submitting;
        form.removeAttribute("aria-busy");
        submitButton.disabled = false;
    }
}
