(function () {
    // A broken product image falls back to the box icon underneath it.
    document.querySelectorAll('[data-product-image]').forEach(function (image) {
        image.addEventListener('error', function () { image.hidden = true; });
        if (image.complete && image.naturalWidth === 0) image.hidden = true;
    });

    const form = document.getElementById('checkout-form');
    if (!form) return;

    const fields = Array.from(form.querySelectorAll('input, select'));
    const status = document.getElementById('checkout-validation-status');
    let checked = false;
    // Handle errors inline instead of interrupting the form with browser popups.
    form.noValidate = true;

    function validateField(field) {
        let message = '';
        const value = field.value.trim();
        if (field.required && !value) message = 'This field is required.';
        else if (field.type === 'email' && value && (field.validity.typeMismatch || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value))) {
            message = 'Enter a valid email address.';
        } else if (field.name === 'zip_code' && value && !/^\d{5}(-\d{4})?$/.test(value)) {
            message = 'Enter a 5-digit ZIP code or ZIP+4 (12345-6789).';
        } else if (!field.validity.valid) message = 'Check this value.';

        document.getElementById(field.id + '-error').textContent = message;
        if (message) field.setAttribute('aria-invalid', 'true');
        else field.removeAttribute('aria-invalid');
        return !message;
    }

    fields.forEach(function (field) {
        field.addEventListener('blur', function () { validateField(field); });
        ['input', 'change'].forEach(function (eventName) {
            field.addEventListener(eventName, function () {
                status.textContent = '';
                if (checked || field.hasAttribute('aria-invalid')) validateField(field);
            });
        });
    });

    form.addEventListener('submit', function (event) {
        event.preventDefault();
        checked = true;
        const invalid = fields.filter(function (field) { return !validateField(field); });
        if (invalid.length) {
            status.textContent = 'Please correct the highlighted fields.';
            status.dataset.error = 'true';
            invalid[0].focus();
        } else {
            delete status.dataset.error;
            status.textContent = 'Your contact and shipping details look valid. No order has been placed or information saved.';
        }
    });
})();
