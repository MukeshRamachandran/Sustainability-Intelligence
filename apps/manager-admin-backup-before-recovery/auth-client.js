const API_BASE = "http://localhost:8000";
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
    const headers = {
        "Content-Type": "application/json",
        ...(options.headers || {})
    };

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

    try {
        data = await response.json();
    } catch {
        data = null;
    }

    if (!response.ok) {
        const message =
            data?.detail ||
            data?.message ||
            `Request failed with status ${response.status}`;

        throw new Error(message);
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