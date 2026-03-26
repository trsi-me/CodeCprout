(function () {
    function closeNav(toggle, drawer, backdrop) {
        if (backdrop) backdrop.hidden = true;
        if (drawer) drawer.classList.remove('nav-open');
        if (toggle) {
            toggle.setAttribute('aria-expanded', 'false');
            var ic = toggle.querySelector('i');
            if (ic) {
                ic.className = 'fa-solid fa-bars';
            }
        }
        document.body.classList.remove('nav-drawer-open');
    }

    function openNav(toggle, drawer, backdrop) {
        if (backdrop) backdrop.hidden = false;
        if (drawer) drawer.classList.add('nav-open');
        if (toggle) {
            toggle.setAttribute('aria-expanded', 'true');
            var ic = toggle.querySelector('i');
            if (ic) {
                ic.className = 'fa-solid fa-xmark';
            }
        }
        document.body.classList.add('nav-drawer-open');
    }

    function isMobileNav() {
        return window.matchMedia('(max-width: 900px)').matches;
    }

    function initNav() {
        var toggle = document.getElementById('nav-toggle');
        var drawer = document.getElementById('main-nav-drawer');
        var backdrop = document.getElementById('nav-backdrop');
        if (!toggle || !drawer) return;

        toggle.addEventListener('click', function () {
            if (!isMobileNav()) return;
            if (drawer.classList.contains('nav-open')) {
                closeNav(toggle, drawer, backdrop);
            } else {
                openNav(toggle, drawer, backdrop);
            }
        });

        if (backdrop) {
            backdrop.addEventListener('click', function () {
                closeNav(toggle, drawer, backdrop);
            });
        }

        drawer.querySelectorAll('a').forEach(function (a) {
            a.addEventListener('click', function () {
                if (isMobileNav()) closeNav(toggle, drawer, backdrop);
            });
        });

        window.addEventListener('resize', function () {
            if (!isMobileNav()) closeNav(toggle, drawer, backdrop);
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && drawer.classList.contains('nav-open')) {
                closeNav(toggle, drawer, backdrop);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initNav);
    } else {
        initNav();
    }
})();
