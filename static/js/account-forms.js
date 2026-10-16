export function passwordChecks(value, digits) {
    const characters = [...value];
    return {
        length: characters.length >= 3,
        number: characters.some((character) => digits.includes(character)),
        bytes: new TextEncoder().encode(value).length <= 72,
    };
}

export async function submitAccountForm(form, message, data) {
    if (form.dataset.submitting === "true") return;
    const submitButton = form.querySelector('button[type="submit"]');
    const buttonText = submitButton.innerHTML;
    form.dataset.submitting = "true";
    form.setAttribute("aria-busy", "true");
    submitButton.disabled = true;
    if (submitButton.dataset.busyLabel) submitButton.innerHTML = submitButton.dataset.busyLabel;
    try {
        const response = await fetch(form.action, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                // the session's CSRF token, printed into the page by base.html
                "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content,
            },
            body: JSON.stringify(data),
        });
        // the rate limiter answers with a page, not JSON
        if (response.status === 429) {
            message.textContent = "Too many attempts. Try again in a minute.";
            return;
        }
        const result = await response.json();

        if (response.ok && result.redirect_url) {
            window.location.href = result.redirect_url;
        } else {
            message.textContent = result.error || "Request failed. Try again.";
        }
    } catch {
        message.textContent = "Request failed. Try again.";
    } finally {
        // Clear secrets and release the form even when the request fails.
        form.querySelectorAll('input[type="password"]').forEach(function (input) {
            input.value = "";
            input.dispatchEvent(new Event("input"));
        });
        delete form.dataset.submitting;
        form.removeAttribute("aria-busy");
        submitButton.disabled = false;
        submitButton.innerHTML = buttonText;
    }
}

export function setupPasswordToggles(form) {
    form.querySelectorAll(".password-toggle").forEach(function (button) {
        const input = document.getElementById(button.getAttribute("aria-controls"));
        button.hidden = false;
        button.addEventListener("click", function () {
            const showing = input.type === "text";
            input.type = showing ? "password" : "text";
            button.textContent = showing ? "Show" : "Hide";
            button.setAttribute("aria-pressed", String(!showing));
            input.focus();
        });
    });

    // always hide the password again before it is sent
    form.addEventListener("submit", function () {
        form.querySelectorAll(".password-toggle").forEach(function (button) {
            document.getElementById(button.getAttribute("aria-controls")).type = "password";
            button.textContent = "Show";
            button.setAttribute("aria-pressed", "false");
        });
    });
}
