const navbar = document.querySelector('.navbar');
const menuToggle = navbar.querySelector('.navbar-toggle');
const menuLabel = menuToggle.querySelector('.navbar-toggle-label');
// keep this breakpoint the same as the mobile CSS
const mobileViewport = window.matchMedia('(max-width: 1100px)');

function setMenuOpen(open) {
    navbar.classList.toggle('menu-open', open);
    menuToggle.setAttribute('aria-expanded', String(open));
    menuLabel.textContent = open ? 'Close' : 'Menu';
}

// only collapse the menu once JS is ready, so links still work without it
menuToggle.hidden = false;
navbar.classList.add('navbar-enhanced');

menuToggle.addEventListener('click', () => {
    setMenuOpen(menuToggle.getAttribute('aria-expanded') !== 'true');
});

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && navbar.classList.contains('menu-open')) {
        setMenuOpen(false);
        // put keyboard focus back on the button after closing
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
    // move focus out of the links before the smaller menu hides them
    if (mobileViewport.matches && navbar.querySelector('.navbar-menu').contains(document.activeElement)) {
        menuToggle.focus();
    }
    setMenuOpen(false);
});
