const home = document.querySelector('.home');

// Tells the CSS it is safe to hide things until they scroll into view.
home.classList.add('home-js');

const revealItems = document.querySelectorAll('[data-reveal]');

if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
        for (const entry of entries) {
            if (entry.isIntersecting) {
                entry.target.classList.add('is-in');
                observer.unobserve(entry.target);
            }
        }
    }, { threshold: 0.15, rootMargin: '0px 0px -8% 0px' });

    revealItems.forEach((item) => observer.observe(item));
} else {
    // very old browsers: just show everything
    revealItems.forEach((item) => item.classList.add('is-in'));
}

const tabList = document.querySelector('.template-tabs');

if (tabList) {
    const tabs = Array.from(tabList.querySelectorAll('[role="tab"]'));
    const panels = tabs.map((tab) => document.getElementById(tab.getAttribute('aria-controls')));

    function selectTab(index, moveFocus) {
        tabs.forEach((tab, i) => {
            const selected = i === index;
            tab.setAttribute('aria-selected', String(selected));
            // only the selected tab is a tab stop; arrow keys move between tabs
            tab.tabIndex = selected ? 0 : -1;
            panels[i].hidden = !selected;
        });
        if (moveFocus) tabs[index].focus();
    }

    tabs.forEach((tab, index) => {
        tab.addEventListener('click', () => selectTab(index, false));
    });

    tabList.addEventListener('keydown', (event) => {
        let next = tabs.indexOf(document.activeElement);

        if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
            next += 1;
            if (next === tabs.length) next = 0;
        } else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
            next -= 1;
            if (next < 0) next = tabs.length - 1;
        } else if (event.key === 'Home') {
            next = 0;
        } else if (event.key === 'End') {
            next = tabs.length - 1;
        } else {
            return;
        }

        event.preventDefault();
        selectTab(next, true);
    });

    tabList.hidden = false;
    selectTab(0, false);
}

const sheet = document.querySelector('.hero-sheet');

if (sheet) {
    const readout = sheet.querySelector('.readout');

    sheet.addEventListener('pointermove', (event) => {
        // touch and pen users do not get a crosshair
        if (event.pointerType !== 'mouse') return;

        const box = sheet.getBoundingClientRect();
        const x = Math.round(event.clientX - box.left);
        const y = Math.round(event.clientY - box.top);

        sheet.style.setProperty('--x', x + 'px');
        sheet.style.setProperty('--y', y + 'px');
        readout.textContent = 'X ' + String(x).padStart(4, '0') + '  Y ' + String(y).padStart(4, '0');
        sheet.classList.add('is-tracking');
    });

    sheet.addEventListener('pointerleave', () => {
        sheet.classList.remove('is-tracking');
    });
}

const tape = document.querySelector('.tape');

if (tape) {
    const tapeValue = tape.querySelector('.tape-value');
    let updateQueued = false;

    function updateTape() {
        const scrollable = document.documentElement.scrollHeight - window.innerHeight;
        const progress = scrollable > 0 ? Math.min(window.scrollY / scrollable, 1) : 0;

        tape.style.setProperty('--p', progress.toFixed(4));

        const totalInches = Math.round(progress * 24 * 12);
        tapeValue.textContent = Math.floor(totalInches / 12) + "'-" + (totalInches % 12) + '"';
        updateQueued = false;
    }

    // Schedule at most one tape update per animation frame.
    window.addEventListener('scroll', () => {
        if (!updateQueued) {
            updateQueued = true;
            requestAnimationFrame(updateTape);
        }
    }, { passive: true });

    updateTape();
}
