document.querySelectorAll('[data-product-image]').forEach(function (image) {
    image.addEventListener('error', function () { image.hidden = true; });
    if (image.complete && image.naturalWidth === 0) image.hidden = true;
});

// Place Order: disable the button after the first click so the order is only sent once.
// (The checkout key in the form also stops a second order on the server.)
const checkoutForm = document.getElementById('checkout-form');
const placeOrderButton = document.getElementById('place-order');
if (checkoutForm && placeOrderButton) {
    checkoutForm.addEventListener('submit', function () {
        placeOrderButton.disabled = true;
        placeOrderButton.textContent = 'Placing order...';
    });
}
