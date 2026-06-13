/**
 * Common utilities shared across all pages.
 * Load BEFORE any page-specific scripts.
 */

// Read CSRF token from the <meta> tag rendered by the server
var CSRF_TOKEN = '';
(function () {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) { CSRF_TOKEN = meta.getAttribute('content') || ''; }
})();

/**
 * Fetch wrapper that auto-injects the CSRF token into every request.
 * Use this instead of raw fetch() for all API calls.
 *
 * Includes a 15-second timeout so the UI never hangs indefinitely.
 */
function apiFetch(url, options) {
    options = options || {};
    options.headers = options.headers || {};
    options.headers['X-CSRF-Token'] = CSRF_TOKEN;

    // Inject CSRF token into JSON body too (belt-and-suspenders)
    if (options.body && typeof options.body === 'string') {
        try {
            var parsed = JSON.parse(options.body);
            parsed.csrf_token = CSRF_TOKEN;
            options.body = JSON.stringify(parsed);
        } catch (e) { /* body is not JSON */ }
    }

    // 15-second timeout — prevents the form from hanging forever
    // if the server is unreachable or stuck
    var controller = new AbortController();
    options.signal = controller.signal;
    var timeoutId = setTimeout(function () {
        controller.abort();
    }, 15000);  // 15 seconds

    return fetch(url, options).finally(function () {
        clearTimeout(timeoutId);
    });
}

// ── Global logout handler ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
    var logoutBtn = document.getElementById('nav-logout');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function (e) {
            e.preventDefault();
            apiFetch('/auth/logout', { method: 'POST' })
                .then(function (resp) { return resp.json(); })
                .then(function (data) {
                    if (data.redirect) {
                        window.location.href = data.redirect;
                    }
                });
        });
    }
});
