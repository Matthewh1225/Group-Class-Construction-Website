const reviewForm = document.getElementById("review-form");

if (reviewForm) {
    const productField = document.getElementById("review-product-field");
    const productSelect = document.getElementById("review-product");
    const productSearch = document.getElementById("product-search");
    const productStatus = document.getElementById("product-search-status");
    const searchUrl = productSearch.dataset.searchUrl;
    const MIN_SEARCH_LENGTH = 2;  // matches PRODUCT_SEARCH_MIN_LENGTH in services/reviews.py
    // The product currently picked ({value, text}), kept in the list while searching for another.
    let selectedProduct = null;
    if (productSelect.value) {
        selectedProduct = { value: productSelect.value, text: productSelect.selectedOptions[0].textContent };
    }
    let searchTimer = null;
    let latestSearch = 0;  // only the newest search may fill the list

    function updateType() {
        const isProduct = reviewForm.elements.review_type.value === "product";
        productField.hidden = !isProduct;
        productSelect.disabled = !isProduct;
        productSelect.required = isProduct;
    }

    function showProducts(products, firstOptionText) {
        const fragment = document.createDocumentFragment();
        fragment.append(new Option(firstOptionText, ""));
        const selectedIsListed = selectedProduct && products.some(product => String(product.id) === selectedProduct.value);
        if (selectedProduct && !selectedIsListed) {
            fragment.append(new Option(selectedProduct.text, selectedProduct.value));
        }
        for (const product of products) {
            const text = product.sku ? `${product.name} · ${product.sku}` : product.name;
            fragment.append(new Option(text, String(product.id)));
        }
        productSelect.replaceChildren(fragment);
        productSelect.value = selectedProduct ? selectedProduct.value : "";
    }

    async function searchProducts() {
        const text = productSearch.value.trim();
        if (text.length < MIN_SEARCH_LENGTH) {
            productStatus.textContent = "Type at least 2 characters of a product name or SKU.";
            return;
        }
        latestSearch += 1;
        const thisSearch = latestSearch;
        productStatus.textContent = "Searching…";
        try {
            const response = await fetch(`${searchUrl}?q=${encodeURIComponent(text)}`, { headers: { Accept: "application/json" } });
            if (!response.ok) throw new Error(`Search failed with status ${response.status}`);
            const data = await response.json();
            if (thisSearch !== latestSearch) return;  // a newer search has started
            const products = data.products;
            showProducts(products, products.length ? "Select a product" : "No matching products");
            if (products.length >= data.limit) {
                productStatus.textContent = `Showing the first ${data.limit} matches. Keep typing to narrow the list.`;
            } else {
                productStatus.textContent = `${products.length} product${products.length === 1 ? "" : "s"} found.`;
            }
        } catch (error) {
            if (thisSearch === latestSearch) productStatus.textContent = "Couldn't search products. Try again.";
        }
    }

    for (const input of reviewForm.querySelectorAll('[name="review_type"]')) {
        input.addEventListener("change", updateType);
    }
    productSelect.addEventListener("change", () => {
        selectedProduct = productSelect.value
            ? { value: productSelect.value, text: productSelect.selectedOptions[0].textContent }
            : null;
    });
    // Wait until typing pauses so each keystroke doesn't send a request.
    productSearch.addEventListener("input", () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(searchProducts, 300);
    });
    document.getElementById("product-search-field").hidden = false;
    productStatus.textContent = "Type a product name or SKU to search.";
    updateType();

    const ratingInputs = Array.from(reviewForm.querySelectorAll('[name="rating"]'));
    function updateRating() {
        const selected = ratingInputs.find(input => input.checked);
        for (const input of ratingInputs) {
            input.closest("label").classList.toggle("is-filled", Boolean(selected) && Number(input.value) <= Number(selected.value));
        }
        document.getElementById("rating-description").textContent = selected
            ? `${selected.value} out of 5 — ${selected.dataset.description}` : "Choose 1 to 5 stars";
    }
    ratingInputs.forEach(input => input.addEventListener("change", updateRating));
    updateRating();

    reviewForm.addEventListener("submit", () => {
        const button = reviewForm.querySelector('button[type="submit"]');
        if (button) {
            button.disabled = true;
            button.textContent = "Publishing…";
            reviewForm.setAttribute("aria-busy", "true");
        }
    });
    // Back/forward cache can restore the form with a disabled submit button.
    window.addEventListener("pageshow", () => {
        const button = reviewForm.querySelector('button[type="submit"]');
        if (button && reviewForm.hasAttribute("aria-busy")) {
            button.disabled = false;
            button.textContent = "Publish review";
            reviewForm.removeAttribute("aria-busy");
        }
    });
}

const reviewError = document.getElementById("review-error");
if (reviewError) reviewError.focus();
