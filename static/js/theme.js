(function () {
    const root = document.documentElement;
    const systemTheme = window.matchMedia('(prefers-color-scheme: light)');
    let savedTheme;

    try {
        savedTheme = localStorage.getItem('buildbetter-theme');
    } catch (error) {
        // The theme still works for this page if browser storage is unavailable.
    }

    if (savedTheme === 'light' || savedTheme === 'dark') {
        root.dataset.theme = savedTheme;
    } else if (systemTheme.matches) {
        root.dataset.theme = 'light';
    } else {
        root.dataset.theme = 'dark';
    }

    function updateButtons() {
        let label = 'Switch to dark mode';
        if (root.dataset.theme === 'dark') {
            label = 'Switch to light mode';
        }
        document.querySelectorAll('.theme-toggle').forEach(function (button) {
            button.setAttribute('aria-label', label);
            button.title = label;
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.theme-toggle').forEach(function (button) {
            button.addEventListener('click', function () {
                if (root.dataset.theme === 'dark') {
                    savedTheme = 'light';
                } else {
                    savedTheme = 'dark';
                }
                root.dataset.theme = savedTheme;
                try {
                    localStorage.setItem('buildbetter-theme', savedTheme);
                } catch (error) {
                    // Keep the selected theme until the page closes.
                }
                updateButtons();
            });
        });
        updateButtons();
    });

    systemTheme.addEventListener('change', function () {
        if (savedTheme !== 'light' && savedTheme !== 'dark') {
            if (systemTheme.matches) {
                root.dataset.theme = 'light';
            } else {
                root.dataset.theme = 'dark';
            }
            updateButtons();
        }
    });
}());
