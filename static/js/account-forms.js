
// Use the same password rules as Python.
export function passwordChecks(value) {
    let characterCount = 0;
    for (const character of value) {
        characterCount += 1;
    }
    return { length: characterCount >= 3, number: /[0-9]/.test(value) };
}

export async function submitAccountForm(form, message, data) {
    const submitButton = form.querySelector('button[type="submit"]');
    const buttonHtml = submitButton.innerHTML;
    submitButton.disabled = true;
    form.setAttribute("aria-busy", "true");
    if (submitButton.dataset.busyLabel) {
        submitButton.textContent = submitButton.dataset.busyLabel;
    }

    try {
        const response = await fetch(form.action, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content,
            },
            body: JSON.stringify(data),
        });
        // Rate-limit errors may be HTML rather than JSON.
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
        for (const input of form.querySelectorAll('input[type="password"]')) {
            input.value = "";
            // Let the password checklist know the field was cleared.
            input.dispatchEvent(new Event("input"));
        }
        form.removeAttribute("aria-busy");
        submitButton.disabled = false;
        submitButton.innerHTML = buttonHtml;
    }
}


function setPasswordVisible(button, visible) {
    const input = document.getElementById(button.getAttribute("aria-controls"));
    if (visible) {
        input.type = "text";
        button.textContent = "Hide";
    } else {
        input.type = "password";
        button.textContent = "Show";
    }
    button.setAttribute("aria-pressed", String(visible));
}

export function setupPasswordToggles(form) {
    const toggles = form.querySelectorAll(".password-toggle");
    for (const button of toggles) {
        button.hidden = false; // Show toggles once JavaScript is ready.
        button.addEventListener("click", function () {
            const input = document.getElementById(button.getAttribute("aria-controls"));
            setPasswordVisible(button, input.type === "password");
            input.focus();
        });
    }

    form.addEventListener("submit", function () {
        for (const button of toggles) {
            setPasswordVisible(button, false);
        }
    });
}

// Google calls handleGoogleSignIn by name after the user picks an account.
export function setupGoogleSignIn(message) {
    window.handleGoogleSignIn = async function (googleResponse) {
        message.textContent = "";
        try {
            const response = await fetch("/google-login", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content,
                },
                body: JSON.stringify({ credential: googleResponse.credential }),
            });
            const result = await response.json();
            if (response.ok && result.redirect_url) {
                window.location.href = result.redirect_url;
            } else {
                message.textContent = result.error || "Google sign-in failed. Try again.";
            }
        } catch {
            message.textContent = "Google sign-in failed. Try again.";
        }
    };
}
