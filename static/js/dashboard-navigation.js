
const sidebar = document.getElementById("dashboard-sidebar");
const menuButton = document.getElementById("dashboard-menu-toggle");
const closeButton = sidebar.querySelector(".dashboard-sidebar-close");
const backdrop = document.querySelector(".dashboard-drawer-backdrop");
const main = document.querySelector(".dashboard-main");
const accountMenu = document.querySelector(".dashboard-account");
// Match the mobile breakpoint in dashboard.css.
const mobile = window.matchMedia("(max-width: 760px)");
let drawerOpen = false;



function setDrawerOpen(open, restoreFocus) {
    const wasOpen = drawerOpen;
    drawerOpen = open && mobile.matches;

    document.body.classList.toggle("dashboard-drawer-open", drawerOpen);
    menuButton.setAttribute("aria-expanded", String(drawerOpen));
    backdrop.hidden = !drawerOpen;
    // Disable the background when open, or the drawer when closed.
    main.inert = drawerOpen;
    sidebar.inert = mobile.matches && !drawerOpen;

    if (drawerOpen) {
        sidebar.setAttribute("role", "dialog");
        sidebar.setAttribute("aria-modal", "true");
        accountMenu.open = false;
        closeButton.focus();
    } else {
        sidebar.removeAttribute("role");
        sidebar.removeAttribute("aria-modal");
        if (wasOpen && restoreFocus) {
            menuButton.focus();
        }
    }
}

menuButton.hidden = false;
document.body.classList.add("dashboard-navigation-ready");
setDrawerOpen(false, false);

menuButton.addEventListener("click", function () {
    setDrawerOpen(true, false);
});
closeButton.addEventListener("click", function () {
    setDrawerOpen(false, true);
});
backdrop.addEventListener("click", function () {
    setDrawerOpen(false, true);
});
for (const link of sidebar.querySelectorAll("a")) {
    link.addEventListener("click", function () {
        if (drawerOpen) {
            setDrawerOpen(false, true);
        }
    });
}

// Escape closes the drawer; Tab stays inside it.
document.addEventListener("keydown", function (event) {
    if (!drawerOpen) {
        return;
    }
    if (event.key === "Escape") {
        event.preventDefault();
        setDrawerOpen(false, true);
        return;
    }
    if (event.key !== "Tab") {
        return;
    }

    const controls = [];
    for (const control of sidebar.querySelectorAll("a[href], button:not(:disabled)")) {
        // Skip hidden links and buttons.
        if (control.getClientRects().length > 0) {
            controls.push(control);
        }
    }
    const first = controls[0];
    const last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
    }
});

mobile.addEventListener("change", function () {
    // Move focus before hiding the sidebar.
    if (mobile.matches && sidebar.contains(document.activeElement)) {
        menuButton.focus();
    }
    setDrawerOpen(false, false);
});



document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && accountMenu.open) {
        accountMenu.open = false;
        accountMenu.querySelector("summary").focus();
    }
});

document.addEventListener("click", function (event) {
    if (!accountMenu.contains(event.target)) {
        accountMenu.open = false;
    }
});



for (const time of document.querySelectorAll("time[data-timestamp]")) {
    const date = new Date(Number(time.dataset.timestamp) * 1000);
    if (!Number.isNaN(date.getTime())) {
        time.dateTime = date.toISOString();
        time.textContent = date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    }
}
