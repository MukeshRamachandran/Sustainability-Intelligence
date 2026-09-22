function routeUser(session) {
    if (!session || !session.user) {
        window.location.href = "login.html";
        return;
    }

    const user = session.user;

    // First-login password-change requirement.
    if (user.must_change_password) {
        window.location.href = "change-password.html";
        return;
    }

    if (user.role === "microcosm_admin") {
        window.location.href = "admin.html";
        return;
    }

    if (user.role === "manager") {
        const allowedDomains = [
            "transport",
            "energy",
            "lpg",
            "water",
            "outreach"
        ];

        if (!allowedDomains.includes(user.manager_domain)) {
            throw new Error("Manager domain is not configured correctly.");
        }

        window.location.href = "manager.html";
        return;
    }

    throw new Error("Unknown account role.");
}