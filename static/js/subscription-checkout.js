const form = document.getElementById('pro-checkout-form');
const plans = JSON.parse(document.getElementById('pro-plan-data').textContent);
const summary = document.getElementById('order-summary');
const submitButton = document.getElementById('subscription-submit');
const buttonLabel = document.getElementById('checkout-button-label');
const errorMessage = document.getElementById('checkout-error');
const discountInput = document.getElementById('subscription-discount-code');
const discountMessage = document.getElementById('subscription-discount-message');
const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });

function updateSummary() {
    const selected = form.querySelector('input[name="plan"]:checked').value;
    const plan = plans[selected];
    summary.dataset.plan = selected;
    document.getElementById('summary-plan').textContent = plan.name;
    document.getElementById('summary-price').textContent = money.format(plan.price / 100);
    const code = discountInput.value.trim();
    let preview = discountPreview(plan.price, 0, code);
    if (!preview) {
        preview = discountPreview(plan.price, 0, '');
        discountMessage.textContent = 'That discount code is not valid.';
    } else {
        discountMessage.textContent = code ? 'Discount code applied.' : '';
    }
    document.getElementById('subscription-discount-row').hidden = preview.discount === 0;
    document.getElementById('subscription-discount-value').textContent = '-' + money.format(preview.discount / 100);
    document.getElementById('subscription-tax').textContent = money.format(preview.tax / 100);
    document.getElementById('summary-total').textContent = money.format(preview.total / 100);
    document.getElementById('summary-billing').textContent = plan.billing;
    document.getElementById('summary-terms').textContent = plan.terms;
    document.getElementById('yearly-savings').hidden = !plan.savings_cents;
    document.getElementById('summary-savings').textContent = money.format(plans.yearly.savings_cents / 100);
    buttonLabel.textContent = plan.button_label;
}

for (const input of form.querySelectorAll('input[name="plan"]')) {
    input.addEventListener('change', updateSummary);
}
discountInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        updateSummary();
    }
});
discountInput.addEventListener('input', function () {
    if (discountMessage.textContent) {
        discountMessage.textContent = '';
    }
});
document.getElementById('subscription-apply-discount').addEventListener('click', updateSummary);

form.addEventListener('submit', function () {
    submitButton.disabled = true;
    submitButton.setAttribute('aria-busy', 'true');
    buttonLabel.textContent = 'Submitting…';
});

// Reset controls when returning with Back.
window.addEventListener('pageshow', function () {
    submitButton.disabled = false;
    submitButton.removeAttribute('aria-busy');
    updateSummary();
});

updateSummary();
if (!errorMessage.hidden) errorMessage.focus();
