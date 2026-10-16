(() => {
    const sidebar = document.getElementById('dashboard-sidebar');
    if (!sidebar) return;

    const menuButton = document.getElementById('dashboard-menu-toggle');
    const closeButton = sidebar.querySelector('.dashboard-sidebar-close');
    const backdrop = document.querySelector('.dashboard-drawer-backdrop');
    const main = document.querySelector('.dashboard-main');
    const account = document.querySelector('.dashboard-account');
    const mobile = window.matchMedia('(max-width: 760px)');
    let open = false;

    function setDrawerOpen(nextOpen, restoreFocus = true) {
        const wasOpen = open;
        open = nextOpen && mobile.matches;
        document.body.classList.toggle('dashboard-drawer-open', open);
        menuButton.setAttribute('aria-expanded', String(open));
        backdrop.hidden = !open;
        // inert blocks background clicks and keyboard focus while the drawer is open.
        main.inert = open;
        sidebar.inert = mobile.matches && !open;
        if (mobile.matches) sidebar.setAttribute('aria-hidden', String(!open));
        else sidebar.removeAttribute('aria-hidden');

        if (open) {
            sidebar.setAttribute('role', 'dialog');
            sidebar.setAttribute('aria-modal', 'true');
            account.open = false;
            closeButton.focus();
        } else {
            sidebar.removeAttribute('role');
            sidebar.removeAttribute('aria-modal');
            if (wasOpen && restoreFocus && mobile.matches) menuButton.focus();
        }
    }

    menuButton.hidden = false;
    document.body.classList.add('dashboard-navigation-ready');
    setDrawerOpen(false);
    menuButton.addEventListener('click', () => setDrawerOpen(true));
    closeButton.addEventListener('click', () => setDrawerOpen(false));
    backdrop.addEventListener('click', () => setDrawerOpen(false));
    sidebar.querySelectorAll('a').forEach((link) => {
        link.addEventListener('click', () => { if (mobile.matches) setDrawerOpen(false); });
    });

    document.addEventListener('keydown', (event) => {
        if (open && event.key === 'Escape') {
            event.preventDefault();
            setDrawerOpen(false);
        } else if (open && event.key === 'Tab') {
            const controls = Array.from(sidebar.querySelectorAll('a[href], button:not(:disabled)'))
                .filter((control) => control.getClientRects().length);
            const first = controls[0];
            const last = controls[controls.length - 1];
            // Keep Tab and Shift+Tab inside the drawer until it closes.
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        } else if (event.key === 'Escape' && account.open) {
            account.open = false;
            account.querySelector('summary').focus();
        }
    });

    document.addEventListener('click', (event) => {
        if (!account.contains(event.target)) account.open = false;
    });
    mobile.addEventListener('change', () => {
        if (mobile.matches && sidebar.contains(document.activeElement)) menuButton.focus();
        // Release background focus and scrolling when switching to desktop.
        setDrawerOpen(false, false);
    });
})();

// Show each saved timestamp (seconds) as a short local date, like "Oct 14, 2026".
// Used by the project list, Project Details and Planning history.
document.querySelectorAll("time[data-timestamp]").forEach(function (time) {
    const date = new Date(Number(time.dataset.timestamp) * 1000);
    if (isNaN(date)) return;
    time.dateTime = date.toISOString();
    time.textContent = date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
});
