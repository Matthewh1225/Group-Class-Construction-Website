(function () {
    // A broken product image falls back to the box icon underneath it.
    document.querySelectorAll('[data-product-image]').forEach(function (image) {
        image.addEventListener('error', function () { image.hidden = true; });
        if (image.complete && image.naturalWidth === 0) image.hidden = true;
    });

})();
