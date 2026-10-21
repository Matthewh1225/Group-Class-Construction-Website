// Clicks and keyboard controls work alongside the CSS hover menu.

const moreCategories = document.querySelector(".category-more");
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

let categoryRequest;

async function filterCategory(url, addHistory = true) {
    if (categoryRequest) categoryRequest.abort();
    const request = new AbortController();
    categoryRequest = request;
    const status = document.getElementById("category-status");
    status.textContent = "Loading products…";
    try {
        const response = await fetch(url, { signal: request.signal });
        if (!response.ok) throw new Error("Product request failed.");
        const page = new DOMParser().parseFromString(await response.text(), "text/html");
        if (request.signal.aborted) return;
        const results = page.querySelector(".catalog-results");
        const search = page.querySelector(".catalog-search");
        if (!results || !search) throw new Error("Product page is missing.");

        const x = window.scrollX;
        const y = window.scrollY;
        document.querySelector(".catalog-results").replaceWith(results);
        document.querySelector(".catalog-search").replaceWith(search);
        for (const link of document.querySelectorAll(".category-nav a")) {
            const selected = Array.from(page.querySelectorAll(".category-nav a")).some(function (item) {
                return item.getAttribute("href") === link.getAttribute("href") && item.hasAttribute("aria-current");
            });
            if (selected) link.setAttribute("aria-current", "page");
            else link.removeAttribute("aria-current");
        }
        moreButton.classList.toggle("is-current", page.querySelector(".category-more-button").classList.contains("is-current"));
        setMoreMenuOpen(false);
        if (moreCategories.contains(document.activeElement)) moreButton.focus({ preventScroll: true });

        // Keep enough height so shorter results do not move the page.
        const missingHeight = y + window.innerHeight - document.documentElement.scrollHeight;
        if (missingHeight > 0) results.style.minHeight = results.offsetHeight + missingHeight + "px";
        if (addHistory) history.pushState(null, "", url);
        window.scrollTo({ left: x, top: y, behavior: "instant" });
        status.textContent = results.querySelector("h2").textContent + " products loaded.";
    } catch (error) {
        if (error.name === "AbortError") return;
        status.classList.remove("sr-only");
        status.textContent = "Could not update products. Please try the category again.";
    }
}

document.addEventListener("click", function (event) {
    const link = event.target.closest(".category-nav a, .catalog-results-head a");
    if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    filterCategory(link.href);
});

window.addEventListener("popstate", function () {
    filterCategory(window.location.href, false);
});
