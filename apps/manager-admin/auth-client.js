const localFrontendPorts = new Set(["3000", "5500", "8080"]);
const API_BASE = window.KCOSMOS_API_BASE || (
    localFrontendPorts.has(window.location.port)
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
        const detail = data?.detail;
        const structuredDetail = detail && typeof detail === "object" && !Array.isArray(detail)
            ? [detail.message, Array.isArray(detail.metrics) && detail.metrics.length
                ? `Missing: ${detail.metrics.join(", ")}.`
                : null].filter(Boolean).join(" ")
            : null;
        const validationDetail = Array.isArray(detail)
            ? detail.map(item => {
                const location = Array.isArray(item?.loc) ? item.loc.slice(1).join(".") : "request";
                return `${location || "request"}: ${item?.msg || "invalid value"}`;
            }).join("; ")
            : null;
        const message =
            data?.error?.message ||
            (typeof detail === "string" ? detail : null) ||
            structuredDetail ||
            validationDetail ||
            data?.message ||
            `Request failed with status ${response.status}`;

        const error = new Error(message);
        error.status = response.status;
        error.code = data?.error?.code || null;
        error.requestId = data?.error?.request_id || response.headers.get("X-Request-ID") || null;
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
