const reviewForm = document.getElementById("review-form");

if (reviewForm) {
    const productField = document.getElementById("review-product-field");
    const productSelect = document.getElementById("review-product");
    const productSearch = document.getElementById("product-search");
    const productStatus = document.getElementById("product-search-status");
    const products = Array.from(productSelect.options).slice(1).map(option => ({
        value: option.value, text: option.textContent,
    }));
    let selectedProduct = productSelect.value;

    function updateType() {
        const isProduct = reviewForm.elements.review_type.value === "product";
        productField.hidden = !isProduct;
        productSelect.disabled = !isProduct;
        productSelect.required = isProduct;
    }

    function filterProducts() {
        const words = productSearch.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
        const matches = products.filter(product => words.every(word => product.text.toLocaleLowerCase().includes(word)));
        const fragment = document.createDocumentFragment();
        fragment.append(new Option(matches.length ? "Select a product" : "No matching products", ""));
        // Keep an existing choice while searching for a replacement.
        const selected = products.find(product => product.value === selectedProduct);
        const keepSelected = selected && !matches.some(product => product.value === selectedProduct);
        if (keepSelected) fragment.append(new Option(selected.text, selected.value));
        for (const product of matches) fragment.append(new Option(product.text, product.value));
        productSelect.replaceChildren(fragment);
        productSelect.value = selectedProduct;
        productStatus.textContent = `${matches.length.toLocaleString()} product${matches.length === 1 ? "" : "s"} found${keepSelected ? "; current selection kept" : ""}.`;
    }

    for (const input of reviewForm.querySelectorAll('[name="review_type"]')) {
        input.addEventListener("change", updateType);
    }
    productSelect.addEventListener("change", () => { selectedProduct = productSelect.value; });
    productSearch.addEventListener("input", filterProducts);
    document.getElementById("product-search-field").hidden = false;
    updateType();
    filterProducts();

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

    const body = document.getElementById("review-body");
    const counter = document.getElementById("review-character-count");
    counter.hidden = false;
    function updateCount() { counter.textContent = `${body.value.length.toLocaleString()} / 2,000`; }
    body.addEventListener("input", updateCount);
    updateCount();

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
