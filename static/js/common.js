/**
 * Common utilities shared across all pages.
 * Load BEFORE any page-specific scripts.
 */

// Read CSRF token from the <meta> tag rendered by the server
var CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.content || '';

/**
 * Fetch wrapper that auto-injects the CSRF token into every request.
 * Use this instead of raw fetch() for all API calls.
 */
async function apiFetch(url, options) {
    options = options || {};
    options.headers = options.headers || {};
    options.headers['X-CSRF-Token'] = CSRF_TOKEN;

    // Also inject into JSON body for routes that expect form data
    if (options.body && typeof options.body === 'string') {
        try {
            var parsed = JSON.parse(options.body);
            parsed.csrf_token = CSRF_TOKEN;
            options.body = JSON.stringify(parsed);
        } catch (e) { /* body is not JSON, leave as-is */ }
    }

    return fetch(url, options);
}

// ── Global logout handler ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
    var logoutBtn = document.getElementById('nav-logout');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async function (e) {
            e.preventDefault();
            var resp = await apiFetch('/auth/logout', { method: 'POST' });
            var data = await resp.json();
            if (data.redirect) {
                window.location.href = data.redirect;
            }
        });
    }
});
