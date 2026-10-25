function useFallbackImage(image) {
    const fallback = image.dataset.fallbackSrc;
    if (!fallback) return;
    // Remove this first so a missing placeholder cannot cause a loop.
    image.removeAttribute("data-fallback-src");
    if (image.src !== new URL(fallback, document.baseURI).href) {
        image.src = fallback;
    }
}

function checkProductImages(container) {
    for (const image of container.querySelectorAll("img[data-fallback-src]")) {
        if (image.complete && image.naturalWidth === 0) {
            useFallbackImage(image);
        }
    }
}

// Use the placeholder when a product image cannot load.
document.addEventListener("error", function (event) {
    if (event.target.matches("img[data-fallback-src]")) {
        useFallbackImage(event.target);
    }
}, true);
checkProductImages(document);

const moreCategories = document.querySelector(".category-more");
if (moreCategories) {
    const moreButton = moreCategories.querySelector(".category-more-button");

    function setMoreMenuOpen(open) {
        moreCategories.classList.toggle("is-open", open);
        moreButton.setAttribute("aria-expanded", String(open));
    }

    moreButton.addEventListener("click", function () {
        const isOpen = moreCategories.classList.contains("is-open");
        setMoreMenuOpen(!isOpen);
    });

    moreCategories.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && moreCategories.classList.contains("is-open")) {
            setMoreMenuOpen(false);
            moreButton.focus();
        }
    });

    // relatedTarget is where focus moves next; null means it left the page.
    moreCategories.addEventListener("focusout", function (event) {
        if (!moreCategories.contains(event.relatedTarget)) {
            setMoreMenuOpen(false);
        }
    });

    document.addEventListener("click", function (event) {
        if (!moreCategories.contains(event.target)) {
            setMoreMenuOpen(false);
        }
    });

}
