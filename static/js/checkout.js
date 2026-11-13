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
