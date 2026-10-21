const navbar = document.querySelector('.navbar');
const menuToggle = navbar.querySelector('.navbar-toggle');
const menuLabel = menuToggle.querySelector('.navbar-toggle-label');
// Match the mobile CSS breakpoint.
const mobileViewport = window.matchMedia('(max-width: 1100px)');

function setMenuOpen(open) {
    navbar.classList.toggle('menu-open', open);
    menuToggle.setAttribute('aria-expanded', String(open));
    menuLabel.textContent = open ? 'Close' : 'Menu';
}

// Keep links visible until JavaScript is ready.
menuToggle.hidden = false;
navbar.classList.add('navbar-enhanced');

menuToggle.addEventListener('click', () => {
    setMenuOpen(menuToggle.getAttribute('aria-expanded') !== 'true');
});

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && navbar.classList.contains('menu-open')) {
        setMenuOpen(false);
        menuToggle.focus();
    }
});

document.addEventListener('click', (event) => {
    if (!navbar.contains(event.target)) setMenuOpen(false);
});

navbar.querySelectorAll('.navbar-menu a').forEach((link) => {
    link.addEventListener('click', () => setMenuOpen(false));
});

mobileViewport.addEventListener('change', () => {
    // Move focus before hiding the mobile links.
    if (mobileViewport.matches && navbar.querySelector('.navbar-menu').contains(document.activeElement)) {
        menuToggle.focus();
    }
    setMenuOpen(false);
});
