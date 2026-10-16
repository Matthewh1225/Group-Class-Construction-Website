import {passwordChecks} from "./account-forms.js";

(() => {
    const workspace = document.getElementById("admin-workspace");
    if (!workspace) return;

    const tableBody = document.getElementById("user-list");
    const search = document.getElementById("admin-search");
    const roleFilter = document.getElementById("admin-role-filter");
    const sortSelect = document.getElementById("admin-sort");
    const directionButton = document.getElementById("admin-sort-direction");
    const pageSizeSelect = document.getElementById("admin-page-size");
    const emptyRow = document.getElementById("admin-empty-row");
    const previous = document.getElementById("admin-prev-page");
    const next = document.getElementById("admin-next-page");
    const state = { sort: "username", direction: "asc", page: 1, pageSize: 10 };
    const collator = new Intl.Collator(undefined, { sensitivity: "base", numeric: true });
    const dateFormatter = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });

    function parseDate(value) {
        if (!value) return null;
        // MySQL timestamps use a space; ISO dates use a T.
        const timestamp = Date.parse(value.trim().replace(" ", "T"));
        return Number.isFinite(timestamp) ? timestamp : null;
    }

    function formatDate(timestamp) {
        return timestamp === null ? "\u2014" : dateFormatter.format(new Date(timestamp));
    }

    const users = Array.from(workspace.querySelectorAll(".admin-user-row")).map((row) => {
        const user = {
            row, id: row.dataset.userId, username: row.dataset.username,
            email: row.dataset.email, role: row.dataset.role, status: row.dataset.status,
            joined: parseDate(row.dataset.joined),
        };
        const time = row.querySelector("[data-user-date]");
        time.textContent = formatDate(user.joined);
        if (user.joined !== null) time.dateTime = new Date(user.joined).toISOString();
        return user;
    });

    function renderUsers() {
        const query = search.value.trim().toLocaleLowerCase();
        const matched = users.filter((user) => {
            const matchesSearch = user.username.toLocaleLowerCase().includes(query) || user.email.toLocaleLowerCase().includes(query);
            let matchesRole = true;
            if (roleFilter.value === "admin") {
                matchesRole = user.role === "admin";
            } else if (roleFilter.value !== "all") {
                matchesRole = user.role !== "admin";
            }
            return matchesSearch && matchesRole;
        });
        matched.sort((a, b) => {
            // Keep missing dates last in either direction.
            if (state.sort === "joined") {
                if (a.joined === null && b.joined !== null) return 1;
                if (b.joined === null && a.joined !== null) return -1;
            }
            let compared;
            if (state.sort === "joined") {
                compared = (a.joined ?? 0) - (b.joined ?? 0);
            } else {
                compared = collator.compare(a[state.sort], b[state.sort]);
            }
            if (compared === 0) return collator.compare(a.id, b.id);
            if (state.direction === "desc") return -compared;
            return compared;
        });
        const pages = Math.max(1, Math.ceil(matched.length / state.pageSize));
        state.page = Math.min(Math.max(1, state.page), pages);
        const start = (state.page - 1) * state.pageSize;
        users.forEach((user) => { user.row.hidden = true; });
        matched.forEach((user, index) => {
            user.row.hidden = index < start || index >= start + state.pageSize;
            tableBody.append(user.row);
        });
        tableBody.append(emptyRow);
        emptyRow.hidden = matched.length > 0;
        document.getElementById("admin-empty-title").textContent = users.length ? "No matching users" : "No users found";
        document.getElementById("admin-empty-description").textContent = users.length ? "Try a different name, email, or role." : "Create an account using Add User.";
        document.getElementById("admin-reset-filters").hidden = !query && roleFilter.value === "all";
        document.getElementById("admin-result-count").textContent = matched.length ? `Showing ${start + 1}\u2013${Math.min(start + state.pageSize, matched.length)} of ${matched.length} users` : "Showing 0 users";
        document.getElementById("admin-page-label").textContent = `Page ${state.page} of ${pages}`;
        previous.disabled = state.page === 1;
        next.disabled = state.page === pages;
        document.getElementById("admin-clear-search").disabled = !search.value;
        directionButton.textContent = state.direction === "asc" ? "\u2191" : "\u2193";
        directionButton.setAttribute("aria-label", state.direction === "asc" ? "Sort descending" : "Sort ascending");
        directionButton.title = directionButton.getAttribute("aria-label");
        workspace.querySelectorAll("[data-sort-column]").forEach((heading) => {
            let sortDescription = "none";
            if (heading.dataset.sortColumn === state.sort) {
                sortDescription = state.direction === "asc" ? "ascending" : "descending";
            }
            heading.setAttribute("aria-sort", sortDescription);
        });
        workspace.querySelectorAll("[data-sort-indicator]").forEach((indicator) => {
            let arrow = "\u2195";
            if (indicator.dataset.sortIndicator === state.sort) {
                arrow = state.direction === "asc" ? "\u2191" : "\u2193";
            }
            indicator.textContent = arrow;
        });
    }

    function resetPage() { state.page = 1; renderUsers(); }
    search.addEventListener("input", resetPage);
    roleFilter.addEventListener("change", resetPage);
    sortSelect.addEventListener("change", () => { state.sort = sortSelect.value; state.direction = "asc"; resetPage(); });
    directionButton.addEventListener("click", () => { state.direction = state.direction === "asc" ? "desc" : "asc"; resetPage(); });
    workspace.querySelectorAll("[data-sort]").forEach((button) => {
        button.addEventListener("click", () => {
            if (state.sort === button.dataset.sort && state.direction === "asc") {
                state.direction = "desc";
            } else {
                state.direction = "asc";
            }
            state.sort = button.dataset.sort;
            sortSelect.value = state.sort;
            resetPage();
        });
    });
    pageSizeSelect.addEventListener("change", () => { state.pageSize = Number(pageSizeSelect.value); resetPage(); });
    previous.addEventListener("click", () => { state.page--; renderUsers(); });
    next.addEventListener("click", () => { state.page++; renderUsers(); });
    document.getElementById("admin-clear-search").addEventListener("click", () => { search.value = ""; resetPage(); search.focus(); });
    document.getElementById("admin-reset-filters").addEventListener("click", () => { search.value = ""; roleFilter.value = "all"; resetPage(); search.focus(); });
    document.getElementById("admin-pagination").hidden = false;
    renderUsers();

    function showSection() {
        const overview = window.location.hash === "#overview";
        document.getElementById("admin-overview").hidden = !overview;
        document.getElementById("user-management").hidden = overview;
        document.getElementById("admin-page-title").textContent = overview ? "Admin Overview" : "User Management";
        document.getElementById("dashboard-header-section").textContent = overview ? "Overview" : "Users";
        document.getElementById("admin-eyebrow").textContent = overview ? "ADMINISTRATION / OVERVIEW" : "ADMINISTRATION / USER MANAGEMENT";
        document.querySelectorAll("[data-admin-nav]").forEach((link) => {
            if ((link.dataset.adminNav === "overview") === overview) link.setAttribute("aria-current", "page");
            else link.removeAttribute("aria-current");
        });
    }
    window.addEventListener("hashchange", showSection);
    showSection();

    workspace.querySelectorAll("[data-close-admin-dialog]").forEach((button) => {
        button.addEventListener("click", () => button.closest("dialog").close());
    });
    const detailsDialog = document.getElementById("admin-details-dialog");
    users.forEach((user) => {
        user.row.querySelector("[data-view-user]").addEventListener("click", () => {
            // textContent keeps user-entered names and emails out of HTML markup.
            document.getElementById("admin-detail-username").textContent = user.username || "\u2014";
            document.getElementById("admin-detail-email").textContent = user.email || "\u2014";
            document.getElementById("admin-detail-role").textContent = user.role === "admin" ? "Admin" : "User";
            document.getElementById("admin-detail-status").textContent = user.status === "disabled" ? "Disabled" : "Active";
            document.getElementById("admin-detail-joined").textContent = formatDate(user.joined);
            document.getElementById("admin-detail-id").textContent = user.id;
            detailsDialog.showModal();
        });
    });

    const disableDialog = document.getElementById("admin-disable-dialog");
    const disableForm = document.getElementById("admin-disable-form");
    users.forEach((user) => {
        const button = user.row.querySelector("[data-disable-user]");
        if (!button) return;
        button.addEventListener("click", () => {
            document.getElementById("admin-disable-username").textContent = user.username;
            disableForm.action = button.dataset.statusUrl;
            disableDialog.showModal();
        });
    });

    // Delete Completely: step 1 is a warning, step 2 asks the admin to type DELETE.
    // The server checks the typed word again, so this is not the only safeguard.
    const deleteDialog = document.getElementById("admin-delete-dialog");
    const deleteWarning = document.getElementById("admin-delete-step-1");
    const deleteForm = document.getElementById("admin-delete-step-2");
    const deleteInput = document.getElementById("admin-delete-confirm");
    const confirmDelete = document.getElementById("admin-confirm-delete");
    users.forEach((user) => {
        const button = user.row.querySelector("[data-delete-user]");
        if (!button) return;
        button.addEventListener("click", () => {
            document.getElementById("admin-delete-username").textContent = user.username;
            deleteForm.action = button.dataset.deleteUrl;
            deleteWarning.hidden = false;
            deleteForm.hidden = true;
            deleteInput.value = "";
            confirmDelete.disabled = true;
            deleteDialog.showModal();
        });
    });
    document.getElementById("admin-delete-continue").addEventListener("click", () => {
        deleteWarning.hidden = true;
        deleteForm.hidden = false;
        deleteInput.focus();
    });
    deleteInput.addEventListener("input", () => {
        confirmDelete.disabled = deleteInput.value !== "DELETE";
    });
    deleteForm.addEventListener("submit", (event) => {
        if (deleteInput.value !== "DELETE") {
            event.preventDefault();
            return;
        }
        confirmDelete.disabled = true;
        confirmDelete.textContent = "Deleting\u2026";
    });

    const addDialog = document.getElementById("admin-add-dialog");
    const addForm = document.getElementById("admin-add-form");
    const createButton = document.getElementById("admin-create-user");
    const serverError = document.getElementById("admin-add-server-error");
    const storageKey = `buildbetter-admin-add-user-${workspace.dataset.currentUserId}`;
    let submitting = false;

    workspace.querySelectorAll("[data-open-add-user]").forEach((button) => {
        button.addEventListener("click", () => { addDialog.showModal(); document.getElementById("admin-username").focus(); });
    });
    workspace.querySelectorAll("[data-toggle-password]").forEach((button) => {
        button.addEventListener("click", () => {
            const input = document.getElementById(button.dataset.togglePassword);
            const visible = input.type === "password";
            input.type = visible ? "text" : "password";
            button.textContent = visible ? "Hide" : "Show";
            button.setAttribute("aria-pressed", String(visible));
            button.setAttribute("aria-label", `${visible ? "Hide" : "Show"} ${input.name === "password" ? "password" : "confirm password"}`);
        });
    });

    function validateField(input) {
        let error = "";
        if (input.name === "username" || input.name === "email") input.value = input.value.trim();
        if (input.validity.valueMissing) error = "This field is required.";
        else if (input.name === "username" && input.value.includes("@")) error = "Usernames cannot contain @.";
        else if (input.name === "email" && input.validity.typeMismatch) error = "Enter a valid email.";
        else if (input.name === "password") {
            const checks = passwordChecks(input.value, addForm.dataset.passwordDigits);
            if (!checks.length) error = "Use at least 3 characters.";
            else if (!checks.bytes) error = "Use no more than 72 UTF-8 bytes.";
            else if (!checks.number) error = "Include at least one number.";
        } else if (input.name === "confirm_password" && input.value !== addForm.elements.password.value) error = "Passwords do not match.";
        input.setAttribute("aria-invalid", String(Boolean(error)));
        document.getElementById(`${input.id}-error`).textContent = error;
        return !error;
    }

    const inputs = Array.from(addForm.querySelectorAll("input:not([type=hidden])"));
    inputs.forEach((input) => {
        input.addEventListener("blur", () => validateField(input));
        input.addEventListener("input", () => {
            if (input.getAttribute("aria-invalid") === "true") validateField(input);
            if (input.name === "password" && addForm.elements.confirm_password.value) validateField(addForm.elements.confirm_password);
        });
    });

    function saveFormState(pending) {
        // Only these three fields survive a redirect. Passwords are never stored.
        try {
            sessionStorage.setItem(storageKey, JSON.stringify({ username: addForm.elements.username.value, email: addForm.elements.email.value, role: addForm.elements.permission_level.value, pending }));
        } catch { /* The form still submits if browser storage is disabled. */ }
    }
    addForm.addEventListener("submit", (event) => {
        if (submitting) { event.preventDefault(); return; }
        const invalidInputs = inputs.filter((input) => !validateField(input));
        if (invalidInputs.length) {
            event.preventDefault();
            invalidInputs[0].focus();
            return;
        }
        saveFormState(true);
        serverError.hidden = true;
        submitting = true;
        createButton.disabled = true;
        createButton.textContent = "Creating\u2026";
    });

    try {
        const saved = JSON.parse(sessionStorage.getItem(storageKey) || "null");
        const error = workspace.querySelector('[data-flash-category="error"]');
        const success = workspace.querySelector('[data-flash-category="success"]');
        if (saved && !success) {
            if (typeof saved.username === "string") addForm.elements.username.value = saved.username;
            if (typeof saved.email === "string") addForm.elements.email.value = saved.email;
            addForm.elements.permission_level.value = saved.role === "admin" ? "admin" : "user";
            if (saved.pending && error) {
                serverError.textContent = error.textContent;
                serverError.hidden = false;
                addDialog.showModal();
            }
            saveFormState(false);
        } else if (saved) sessionStorage.removeItem(storageKey);
    } catch { /* Missing or blocked storage should not stop the dashboard. */ }

    // Back navigation can restore disabled buttons from a cached page.
    window.addEventListener("pageshow", (event) => {
        submitting = false;
        createButton.disabled = false;
        createButton.textContent = "Create User";
        confirmDelete.disabled = deleteInput.value !== "DELETE";
        confirmDelete.textContent = "Delete Completely";
        if (event.persisted) {
            addForm.elements.password.value = "";
            addForm.elements.confirm_password.value = "";
        }
    });
})();
