/* The supported local Manager/Admin origin is port 3000, which is the only
   origin in the backend's ALLOWED_ORIGINS (see services/main-api/.env.example
   and compose.yaml).  These two lists must stay in agreement: a port listed
   here but missing from ALLOWED_ORIGINS resolves the API correctly and is then
   blocked by CORS, which is harder to diagnose than no API base at all.

   To serve the portal from another port, set window.KCOSMOS_API_BASE before
   this script AND add that exact origin to ALLOWED_ORIGINS. Never use a
   wildcard origin: the session cookie is sent with credentials. */
const SUPPORTED_FRONTEND_PORT = "3000";
const API_BASE = window.KCOSMOS_API_BASE || (
    window.location.port === SUPPORTED_FRONTEND_PORT
        ? `${window.location.protocol}//${window.location.hostname}:8000`
        : ""
);
const CSRF_COOKIE_NAME = "microcosm_csrf";

function getCookie(name) {
    const cookies = document.cookie.split(";");

    for (const cookie of cookies) {
        const [key, ...valueParts] = cookie.trim().split("=");

        if (key === name) {
            return decodeURIComponent(valueParts.join("="));
        }
    }

    return null;
}

async function apiRequest(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
        headers["Content-Type"] = "application/json";
    }

    if (options.csrf === true) {
        const csrfToken = getCookie(CSRF_COOKIE_NAME);

        if (!csrfToken) {
            throw new Error("CSRF token is missing. Please sign in again.");
        }

        headers["X-CSRF-Token"] = csrfToken;
    }

    const response = await fetch(`${API_BASE}${path}`, {
        credentials: "include",
        ...options,
        headers
    });

    let data = null;

    // A successful DELETE may legitimately return 204 No Content.  Do not
    // attempt JSON parsing in that case; callers only need the successful
    // response contract, not a synthetic body.
    if (response.status !== 204) {
        try {
            data = await response.json();
        } catch {
            data = null;
        }
    }

    if (!response.ok) {
        // This backend always wraps errors as {"error": {...}}; it never
        // returns a top-level "detail" key (see error_payload() in
        // app/main.py). Structured metadata an HTTPException attaches, such
        // as "metrics" or "blockers", is merged directly into data.error by
        // the shared exception handler, not into a "detail" object.
        const errorBody = data?.error;
        const enrichment = errorBody && typeof errorBody === "object"
            ? [
                Array.isArray(errorBody.metrics) && errorBody.metrics.length
                    ? `Missing: ${errorBody.metrics.join(", ")}.`
                    : null,
                Array.isArray(errorBody.blockers) && errorBody.blockers.length
                    ? `Blocking: ${errorBody.blockers.map(item => `${item.domain} (${item.status || item.reason || "not approved"})`).join(", ")}.`
                    : null
              ].filter(Boolean).join(" ")
            : "";
        const detail = data?.detail;
        const validationDetail = Array.isArray(detail)
            ? detail.map(item => {
                const location = Array.isArray(item?.loc) ? item.loc.slice(1).join(".") : "request";
                return `${location || "request"}: ${item?.msg || "invalid value"}`;
            }).join("; ")
            : null;
        const baseMessage =
            errorBody?.message ||
            (typeof detail === "string" ? detail : null) ||
            validationDetail ||
            data?.message ||
            `Request failed with status ${response.status}`;
        const message = enrichment ? `${baseMessage} ${enrichment}` : baseMessage;

        const error = new Error(message);
        error.status = response.status;
        error.code = errorBody?.code || null;
        error.requestId = errorBody?.request_id || response.headers.get("X-Request-ID") || null;
        throw error;
    }

    return data;
}

async function login(username, password) {
    return apiRequest("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
            username,
            password
        })
    });
}

async function getSession() {
    return apiRequest("/api/auth/session", {
        method: "GET"
    });
}

async function changePassword(currentPassword, newPassword) {
    return apiRequest("/api/auth/change-password", {
        method: "POST",
        csrf: true,
        body: JSON.stringify({
            current_password: currentPassword,
            new_password: newPassword
        })
    });
}

async function logout() {
    return apiRequest("/api/auth/logout", {
        method: "POST",
        csrf: true
    });
}

function apiUrl(path) {
    return `${API_BASE}${path}`;
}

window.KCOSMOS_API_URL = apiUrl;
