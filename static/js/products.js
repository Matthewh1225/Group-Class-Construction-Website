function useFallbackImage(image) {
    const fallback = image.dataset.fallbackSrc;
    if (!fallback) return;
    // Remove the fallback to prevent repeated image errors.
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

// Use the placeholder if an image fails to load.
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

    setMoreMenuOpen(false);

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

    // relatedTarget is the next focused element.
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
