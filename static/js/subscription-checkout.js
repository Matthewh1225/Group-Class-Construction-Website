const form = document.getElementById('pro-checkout-form');
const plans = JSON.parse(document.getElementById('pro-plan-data').textContent);
const summary = document.getElementById('order-summary');
const submitButton = document.getElementById('subscription-submit');
const buttonLabel = document.getElementById('checkout-button-label');
const errorMessage = document.getElementById('checkout-error');
const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });

function updateSummary() {
    const selected = form.querySelector('input[name="plan"]:checked').value;
    const plan = plans[selected];
    summary.dataset.plan = selected;
    document.getElementById('summary-plan').textContent = plan.name;
    document.getElementById('summary-price').textContent = money.format(plan.price / 100);
    document.getElementById('summary-total').textContent = money.format(plan.price / 100);
    document.getElementById('summary-billing').textContent = plan.billing;
    document.getElementById('summary-terms').textContent = plan.terms;
    document.getElementById('yearly-savings').hidden = !plan.savings_cents;
    document.getElementById('summary-savings').textContent = money.format(plans.yearly.savings_cents / 100);
    buttonLabel.textContent = plan.button_label;
}

for (const input of form.querySelectorAll('input[name="plan"]')) {
    input.addEventListener('change', updateSummary);
}

form.addEventListener('submit', function () {
    submitButton.disabled = true;
    submitButton.setAttribute('aria-busy', 'true');
    buttonLabel.textContent = 'Checking checkout…';
});

// Restore the controls when the browser Back button brings this page back.
window.addEventListener('pageshow', function () {
    submitButton.disabled = false;
    submitButton.removeAttribute('aria-busy');
    updateSummary();
});

updateSummary();
if (!errorMessage.hidden) errorMessage.focus();
