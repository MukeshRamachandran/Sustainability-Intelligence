(function () {
    const destinations = {
        microcosm_admin: "admin-overview.html",
        transport: "transport-entry.html",
        energy: "energy-entry.html",
        lpg: "lpg-entry.html",
        water: "water-entry.html",
        outreach: "community-outreach-entry.html",
        waste: "waste-entry.html"
    };

    const loginPages = {
        microcosm_admin: "admin-login.html",
        transport: "transport-login.html",
        energy: "energy-login.html",
        lpg: "lpg-login.html",
        water: "water-login.html",
        outreach: "outreach-login.html",
        waste: "waste-login.html"
    };

    let currentUser = null;

    function isExpectedUser(user, role, domain) {
        if (!user || user.role !== role) return false;
        return role !== "manager" || domain === null || user.manager_domain === domain;
    }

    function destinationFor(user) {
        if (user?.role === "microcosm_admin") return destinations.microcosm_admin;
        if (user?.role === "manager") return destinations[user.manager_domain] || "index.html";
        return "index.html";
    }

    function loginFor(role, domain) {
        return role === "microcosm_admin"
            ? loginPages.microcosm_admin
            : (loginPages[domain] || "index.html");
    }

    function routeAuthenticatedUser(session) {
        const user = session?.user;
        if (!user) {
            window.location.replace("index.html");
            return;
        }
        if (user.must_change_password) {
            window.location.replace("change-password.html");
            return;
        }
        window.location.replace(destinationFor(user));
    }

    async function guardPage(role, domain, loginPage) {
        try {
            const session = await getSession();
            const user = session?.user;
            if (!isExpectedUser(user, role, domain)) {
                window.location.replace(loginPage || loginFor(role, domain));
                return null;
            }
            if (user.must_change_password) {
                window.location.replace("change-password.html");
                return null;
            }
            currentUser = user;
            document.documentElement.classList.add("auth-verified");
            return session;
        } catch (_) {
            window.location.replace(loginPage || loginFor(role, domain));
            return null;
        }
    }

    async function logoutTo(loginPage) {
        try { await logout(); } catch (_) { /* redirect even if the session already expired */ }
        currentUser = null;
        window.location.replace(loginPage || "index.html");
    }

    window.KCosmosAuth = {
        destinations,
        loginPages,
        isExpectedUser,
        destinationFor,
        routeAuthenticatedUser,
        guardPage,
        logoutTo,
        getCurrentUser: () => currentUser
    };

    // Compatibility for existing submission metadata; this is in-memory session data,
    // never localStorage/sessionStorage authentication state.
    window.getCurrentUser = () => currentUser;

    const protectedPage = document.body?.dataset.authRole;
    if (protectedPage) {
        const role = document.body.dataset.authRole;
        const domain = document.body.dataset.authDomain || null;
        const loginPage = document.body.dataset.loginPage;
        guardPage(role, domain, loginPage);

        // A protected document restored from the browser back/forward cache may
        // still contain data rendered before logout. Hide and revalidate it.
        window.addEventListener("pageshow", event => {
            if (!event.persisted) return;
            document.documentElement.classList.remove("auth-verified");
            guardPage(role, domain, loginPage);
        });

        document.addEventListener("DOMContentLoaded", () => {
            const logoutButton = document.getElementById("logout-btn");
            if (logoutButton) {
                logoutButton.addEventListener("click", event => {
                    event.preventDefault();
                    logoutTo(loginPage);
                });
            }
        });
    }
})();
