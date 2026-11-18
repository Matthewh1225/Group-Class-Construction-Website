document.querySelectorAll('[data-product-image]').forEach(function (image) {
    image.addEventListener('error', function () { image.hidden = true; });
    if (image.complete && image.naturalWidth === 0) image.hidden = true;
});

const checkoutForm = document.getElementById('checkout-form');
const placeOrderButton = document.getElementById('place-order');
if (checkoutForm && placeOrderButton) {
    const originalText = placeOrderButton.textContent;
    const originallyDisabled = placeOrderButton.disabled;

    checkoutForm.addEventListener('submit', function () {
        placeOrderButton.disabled = true;
        placeOrderButton.textContent = 'Placing order...';
    });

    window.addEventListener('pageshow', function () {
        placeOrderButton.disabled = originallyDisabled;
        placeOrderButton.textContent = originalText;
    });
}

const discountInput = document.getElementById('discount-code');
const applyDiscountButton = document.getElementById('apply-discount');
const discountMessage = document.getElementById('discount-message');
const discountRow = document.getElementById('checkout-discount-row');
const discountValue = document.getElementById('checkout-discount-value');
const discountLabel = document.getElementById('discount-label');
const discountedSubtotalRow = document.getElementById('discounted-subtotal-row');
const discountedSubtotalValue = document.getElementById('discounted-subtotal-value');
const taxValue = document.querySelector('[data-tax-value]');
const totalValue = document.querySelector('[data-total-value]');
const shippingValue = document.querySelector('[data-shipping-value]');
const shippingRadios = document.querySelectorAll('input[name="shipping_method"]');
const summary = document.querySelector('.shopping-summary');

if (discountInput && applyDiscountButton && discountMessage && discountRow &&
    discountValue && taxValue && totalValue && summary) {
    const subtotalCents = Number(summary.dataset.subtotalCents);
    let shippingCents = Number(summary.dataset.shippingCents || 0);
    let appliedCode = (summary.dataset.discountCode || discountInput.value || '').trim();

    const formatMoney = function (cents) {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD'
        }).format(cents / 100);
    };

    const renderTotals = function (preview, code) {
        discountValue.textContent = '-' + formatMoney(preview.discount);
        taxValue.textContent = formatMoney(preview.tax);
        totalValue.textContent = formatMoney(preview.total);
        discountRow.hidden = preview.discount === 0;
        if (discountLabel) {
            discountLabel.textContent = code && preview.percentage
                ? 'Discount (' + code.toUpperCase() + ', ' + preview.percentage + '%)'
                : 'Discount';
        }
        if (discountedSubtotalRow && discountedSubtotalValue) {
            discountedSubtotalRow.hidden = true;
        }
    };

    const handleApply = function () {
        const code = discountInput.value.trim();
        if (!code) {
            appliedCode = '';
            discountMessage.textContent = '';
            const preview = discountPreview(subtotalCents, shippingCents, '');
            renderTotals(preview, '');
            return;
        }

        const preview = discountPreview(subtotalCents, shippingCents, code);
        if (!preview) {
            discountMessage.textContent = 'That discount code is not valid.';
        } else {
            appliedCode = code;
            discountMessage.textContent = 'Discount code applied.';
            renderTotals(preview, code);
        }
    };

    applyDiscountButton.addEventListener('click', handleApply);
    discountInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            handleApply();
        }
    });

    discountInput.addEventListener('input', function () {
        if (discountMessage.textContent) {
            discountMessage.textContent = '';
        }
    });

    shippingRadios.forEach(function (radio) {
        radio.addEventListener('change', function () {
            if (radio.checked && radio.dataset.priceCents !== undefined) {
                shippingCents = Number(radio.dataset.priceCents);
                summary.dataset.shippingCents = shippingCents;
                if (shippingValue) {
                    shippingValue.textContent = formatMoney(shippingCents);
                }
                const preview = discountPreview(subtotalCents, shippingCents, appliedCode);
                if (preview) {
                    renderTotals(preview, appliedCode);
                }
            }
        });
    });

    if (checkoutForm) {
        checkoutForm.addEventListener('submit', function () {
            discountInput.value = appliedCode;
        });
    }

    if (appliedCode) {
        const preview = discountPreview(subtotalCents, shippingCents, appliedCode);
        if (preview) {
            renderTotals(preview, appliedCode);
        }
    }
}
