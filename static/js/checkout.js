document.querySelectorAll('[data-product-image]').forEach(function (image) {
    image.addEventListener('error', function () { image.hidden = true; });
    if (image.complete && image.naturalWidth === 0) image.hidden = true;
});

// TODO: the server does not check checkout_key yet; create_order must block duplicate orders.
const checkoutForm = document.getElementById('checkout-form');
const placeOrderButton = document.getElementById('place-order');
if (checkoutForm && placeOrderButton) {
    checkoutForm.addEventListener('submit', function () {
        placeOrderButton.disabled = true;
        placeOrderButton.textContent = 'Placing order...';
    });
}
