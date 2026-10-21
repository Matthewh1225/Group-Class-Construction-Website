import {passwordChecks, setupPasswordToggles} from "./account-forms.js";


const workspace = document.getElementById("admin-workspace");
const tableBody = document.getElementById("user-list");
const search = document.getElementById("admin-search");
const roleFilter = document.getElementById("admin-role-filter");
const sortSelect = document.getElementById("admin-sort");
const directionButton = document.getElementById("admin-sort-direction");
const pageSizeSelect = document.getElementById("admin-page-size");
const emptyRow = document.getElementById("admin-empty-row");
const previousButton = document.getElementById("admin-prev-page");
const nextButton = document.getElementById("admin-next-page");

const deleteWarning = document.getElementById("admin-delete-step-1");
const deleteForm = document.getElementById("admin-delete-step-2");
const deleteInput = document.getElementById("admin-delete-confirm");
const confirmDelete = document.getElementById("admin-confirm-delete");

const addDialog = document.getElementById("admin-add-dialog");
const addForm = document.getElementById("admin-add-form");
const createButton = document.getElementById("admin-create-user");
const serverError = document.getElementById("admin-add-server-error");

const state = { sort: "username", direction: "asc", page: 1, pageSize: 10 };

// Sort names like user2 before user10.
const collator = new Intl.Collator(undefined, { sensitivity: "base", numeric: true });
const dateFormatter = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });



function parseDate(value) {
    if (!value) {
        return null;
    }
    // Use T so browsers read the date correctly.
    const timestamp = Date.parse(value.trim().replace(" ", "T"));
    if (Number.isNaN(timestamp)) {
        return null;
    }
    return timestamp;
}

function formatDate(timestamp) {
    if (timestamp === null) {
        return "—"; 
    }
    return dateFormatter.format(new Date(timestamp));
}

const users = [];
for (const row of document.querySelectorAll(".admin-user-row")) {
    const user = {
        row: row,
        id: row.dataset.userId,
        username: row.dataset.username,
        email: row.dataset.email,
        role: row.dataset.role,
        status: row.dataset.status,
        joined: parseDate(row.dataset.joined),
    };
    const time = row.querySelector("[data-user-date]");
    time.textContent = formatDate(user.joined);
    if (user.joined !== null) {
        time.dateTime = new Date(user.joined).toISOString();
    }
    users.push(user);
}


function userMatches(user, query) {
    const nameMatches = user.username.toLocaleLowerCase().includes(query);
    const emailMatches = user.email.toLocaleLowerCase().includes(query);
    if (!nameMatches && !emailMatches) {
        return false;
    }
    if (roleFilter.value === "admin") {
        return user.role === "admin";
    }
    if (roleFilter.value === "user") {
        return user.role !== "admin";
    }
    return true; 
}

function compareUsers(a, b) {
    let compared;
    if (state.sort === "joined") {
        // Always put missing dates last.
        if (a.joined === null && b.joined === null) {
            return collator.compare(a.id, b.id);
        }
        if (a.joined === null) {
            return 1;
        }
        if (b.joined === null) {
            return -1;
        }
        compared = a.joined - b.joined;
    } else {

        compared = collator.compare(a[state.sort], b[state.sort]);
    }

    if (compared === 0) {
        return collator.compare(a.id, b.id);
    }
    if (state.direction === "desc") {
        return -compared;
    }
    return compared;
}

function showPage(matched) {
    const pageCount = Math.max(1, Math.ceil(matched.length / state.pageSize));
    if (state.page < 1) {
        state.page = 1;
    }
    if (state.page > pageCount) {
        state.page = pageCount;
    }
    const start = (state.page - 1) * state.pageSize; 
    const end = start + state.pageSize;              

    for (const user of users) {
        user.row.hidden = true;
    }
    // Appending existing rows moves them without recreating them.
    for (let index = 0; index < matched.length; index++) {
        const row = matched[index].row;
        row.hidden = index < start || index >= end;
        tableBody.append(row);
    }
    tableBody.append(emptyRow);
    emptyRow.hidden = matched.length > 0;

    let emptyTitle = "No users found";
    if (users.length > 0) {
        emptyTitle = "No matching users";
    }
    document.getElementById("admin-empty-title").textContent = emptyTitle;

    let countText = "Showing 0 users";
    if (matched.length > 0) {
        const lastShown = Math.min(end, matched.length);
        countText = `Showing ${start + 1}–${lastShown} of ${matched.length} users`;
    }
    document.getElementById("admin-result-count").textContent = countText;
    document.getElementById("admin-page-label").textContent = `Page ${state.page} of ${pageCount}`;
    previousButton.disabled = state.page === 1;
    nextButton.disabled = state.page === pageCount;
}

function updateSortLabels() {
    const ascending = state.direction === "asc";
    let arrow = "↓"; 
    let nextDirectionLabel = "Sort ascending";
    if (ascending) {
        arrow = "↑"; 
        nextDirectionLabel = "Sort descending";
    }
    directionButton.textContent = arrow;
    directionButton.setAttribute("aria-label", nextDirectionLabel);
    directionButton.title = nextDirectionLabel;

    for (const heading of document.querySelectorAll("[data-sort-column]")) {
        if (heading.dataset.sortColumn !== state.sort) {
            heading.setAttribute("aria-sort", "none");
        } else if (ascending) {
            heading.setAttribute("aria-sort", "ascending");
        } else {
            heading.setAttribute("aria-sort", "descending");
        }
    }
    for (const indicator of document.querySelectorAll("[data-sort-indicator]")) {
        if (indicator.dataset.sortIndicator === state.sort) {
            indicator.textContent = arrow;
        } else {
            indicator.textContent = "↕";
        }
    }
}

function renderUsers() {
    const query = search.value.trim().toLocaleLowerCase();
    const matched = [];
    for (const user of users) {
        if (userMatches(user, query)) {
            matched.push(user);
        }
    }
    matched.sort(compareUsers);

    showPage(matched);
    updateSortLabels();
    document.getElementById("admin-clear-search").disabled = search.value === "";
    document.getElementById("admin-reset-filters").hidden = query === "" && roleFilter.value === "all";
}

function showFirstPage() {
    state.page = 1;
    renderUsers();
}

function setupUserTable() {
    search.addEventListener("input", showFirstPage);
    roleFilter.addEventListener("change", showFirstPage);

    sortSelect.addEventListener("change", function () {
        state.sort = sortSelect.value;
        state.direction = "asc";
        showFirstPage();
    });

    directionButton.addEventListener("click", function () {
        if (state.direction === "asc") {
            state.direction = "desc";
        } else {
            state.direction = "asc";
        }
        showFirstPage();
    });

    for (const button of document.querySelectorAll("[data-sort]")) {
        button.addEventListener("click", function () {
            if (state.sort === button.dataset.sort && state.direction === "asc") {
                state.direction = "desc";
            } else {
                state.direction = "asc";
            }
            state.sort = button.dataset.sort;
            sortSelect.value = state.sort;
            showFirstPage();
        });
    }

    pageSizeSelect.addEventListener("change", function () {
        state.pageSize = Number(pageSizeSelect.value);
        showFirstPage();
    });
    previousButton.addEventListener("click", function () {
        state.page = state.page - 1;
        renderUsers();
    });
    nextButton.addEventListener("click", function () {
        state.page = state.page + 1;
        renderUsers();
    });

    document.getElementById("admin-clear-search").addEventListener("click", function () {
        search.value = "";
        showFirstPage();
        search.focus();
    });
    document.getElementById("admin-reset-filters").addEventListener("click", function () {
        search.value = "";
        roleFilter.value = "all";
        showFirstPage();
        search.focus();
    });

    document.getElementById("admin-pagination").hidden = false;
    renderUsers();
}



// Use textContent so user data is never treated as HTML.
function showUserDetails(user) {
    let role = "User";
    if (user.role === "admin") {
        role = "Admin";
    }
    let status = "Active";
    if (user.status === "disabled") {
        status = "Disabled";
    }
    document.getElementById("admin-detail-username").textContent = user.username || "—";
    document.getElementById("admin-detail-email").textContent = user.email || "—";
    document.getElementById("admin-detail-role").textContent = role;
    document.getElementById("admin-detail-status").textContent = status;
    document.getElementById("admin-detail-joined").textContent = formatDate(user.joined);
    document.getElementById("admin-detail-id").textContent = user.id;
    document.getElementById("admin-details-dialog").showModal();
}

function openDisableDialog(user, statusUrl) {
    document.getElementById("admin-disable-username").textContent = user.username;
    document.getElementById("admin-disable-form").action = statusUrl;
    document.getElementById("admin-disable-dialog").showModal();
}

function openDeleteDialog(user, deleteUrl) {
    document.getElementById("admin-delete-username").textContent = user.username;
    deleteForm.action = deleteUrl;
    deleteWarning.hidden = false;
    deleteForm.hidden = true;
    deleteInput.value = "";
    confirmDelete.disabled = true;
    document.getElementById("admin-delete-dialog").showModal();
}

function setupRowButtons() {
    for (const button of document.querySelectorAll("[data-close-admin-dialog]")) {
        button.addEventListener("click", function () {
            button.closest("dialog").close();
        });
    }

    for (const user of users) {
        user.row.querySelector("[data-view-user]").addEventListener("click", function () {
            showUserDetails(user);
        });

        const disableButton = user.row.querySelector("[data-disable-user]");
        if (disableButton !== null) {
            disableButton.addEventListener("click", function () {
                openDisableDialog(user, disableButton.dataset.statusUrl);
            });
        }
        const deleteButton = user.row.querySelector("[data-delete-user]");
        if (deleteButton !== null) {
            deleteButton.addEventListener("click", function () {
                openDeleteDialog(user, deleteButton.dataset.deleteUrl);
            });
        }
    }

    document.getElementById("admin-delete-continue").addEventListener("click", function () {
        deleteWarning.hidden = true;
        deleteForm.hidden = false;
        deleteInput.focus();
    });
    deleteInput.addEventListener("input", function () {
        confirmDelete.disabled = deleteInput.value !== "DELETE";
    });
    deleteForm.addEventListener("submit", function (event) {
        if (deleteInput.value !== "DELETE") {
            event.preventDefault();
            return;
        }
        confirmDelete.disabled = true;
        confirmDelete.textContent = "Deleting…";
    });

    // Reset form controls when the Back button restores this page.
    window.addEventListener("pageshow", function () {
        confirmDelete.disabled = deleteInput.value !== "DELETE";
        confirmDelete.textContent = "Delete Completely";
    });
}



function validateField(input) {
    if (input.name === "username" || input.name === "email") {
        input.value = input.value.trim();
    }

    let error = "";
    if (input.validity.valueMissing) {
        error = "This field is required.";
    } else if (input.name === "username" && input.value.includes("@")) {
        error = "Usernames cannot contain @.";
    } else if (input.name === "email" && input.validity.typeMismatch) {
        error = "Enter a valid email.";
    } else if (input.name === "password") {
        const checks = passwordChecks(input.value, addForm.dataset.passwordDigits);
        if (!checks.length) {
            error = "Use at least 3 characters.";
        } else if (!checks.number) {
            error = "Include at least one number.";
        }
    } else if (input.name === "confirm_password" && input.value !== addForm.elements.password.value) {
        error = "Passwords do not match.";
    }

    input.setAttribute("aria-invalid", String(error !== ""));
    document.getElementById(input.id + "-error").textContent = error;
    return error === "";
}

// Keep each admin's saved form values separate.
const storageKey = "buildbetter-admin-add-user-" + workspace.dataset.currentUserId;

// Restore non-password fields after a failed submission.
function saveTypedValues() {
    const values = {
        username: addForm.elements.username.value,
        email: addForm.elements.email.value,
        role: addForm.elements.permission_level.value,
    };
    try {
        sessionStorage.setItem(storageKey, JSON.stringify(values));
    } catch {
        // The form still works without browser storage.
    }
}

function restoreAddUserForm() {
    let saved = null;
    try {
        const savedText = sessionStorage.getItem(storageKey);
        sessionStorage.removeItem(storageKey);
        saved = JSON.parse(savedText); 
    } catch {
        return;
    }

    const error = document.querySelector('[data-flash-category="error"]');
    if (saved === null || error === null) {
        return;
    }
    addForm.elements.username.value = saved.username;
    addForm.elements.email.value = saved.email;
    addForm.elements.permission_level.value = saved.role;
    serverError.textContent = error.textContent;
    serverError.hidden = false;
    addDialog.showModal();
}

function setupAddUserForm() {
    const fields = addForm.querySelectorAll("input:not([type=hidden])");

    for (const button of document.querySelectorAll("[data-open-add-user]")) {
        button.addEventListener("click", function () {
            addDialog.showModal();
            document.getElementById("admin-username").focus();
        });
    }
    setupPasswordToggles(addForm);

    for (const input of fields) {
        input.addEventListener("blur", function () {
            validateField(input);
        });
        input.addEventListener("input", function () {
            if (input.getAttribute("aria-invalid") === "true") {
                validateField(input);
            }
            if (input.name === "password" && addForm.elements.confirm_password.value !== "") {
                validateField(addForm.elements.confirm_password);
            }
        });
    }

    addForm.addEventListener("submit", function (event) {
        let firstInvalid = null;
        for (const input of fields) {
            const valid = validateField(input);
            if (!valid && firstInvalid === null) {
                firstInvalid = input;
            }
        }
        if (firstInvalid !== null) {
            event.preventDefault();
            firstInvalid.focus();
            return;
        }

        saveTypedValues();
        serverError.hidden = true;
        createButton.disabled = true;
        createButton.textContent = "Creating…";
    });

    // Reset form controls when the Back button restores this page.
    window.addEventListener("pageshow", function (event) {
        createButton.disabled = false;
        createButton.textContent = "Create User";
        if (event.persisted) {
            addForm.elements.password.value = "";
            addForm.elements.confirm_password.value = "";
        }
    });

    restoreAddUserForm();
}



if (tableBody !== null) {
    setupUserTable();
    setupRowButtons();
    setupAddUserForm();
}
