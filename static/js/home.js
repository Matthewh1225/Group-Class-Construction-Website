const home = document.querySelector('.home');

home.classList.add('home-js');

function revealVisibleItems(entries) {
    for (const entry of entries) {
        if (entry.isIntersecting) {
            entry.target.classList.add('is-in');
            revealObserver.unobserve(entry.target);
        }
    }
}

const revealObserver = new IntersectionObserver(revealVisibleItems, { threshold: 0.15, rootMargin: '0px 0px -8% 0px' });
for (const item of document.querySelectorAll('[data-reveal]')) {
    revealObserver.observe(item);
}

const sheet = document.querySelector('.hero-sheet');

if (sheet) {
    const readout = sheet.querySelector('.readout');

    sheet.addEventListener('pointermove', (event) => {
        // Only show the crosshair for a mouse.
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

    // Update the tape at most once per animation frame.
    window.addEventListener('scroll', () => {
        if (!updateQueued) {
            updateQueued = true;
            requestAnimationFrame(updateTape);
        }
    }, { passive: true });

    updateTape();
}
