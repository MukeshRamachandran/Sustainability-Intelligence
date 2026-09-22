async function requireAdminPage() {
    try {
        const session = await getSession();

        if (session.user.must_change_password) {
            window.location.href = "change-password.html";
            return null;
        }

        if (session.user.role !== "microcosm_admin") {
            routeUser(session);
            return null;
        }

        return session;

    } catch (error) {
        window.location.href = "login.html";
        return null;
    }
}


async function requireManagerPage() {
    try {
        const session = await getSession();

        if (session.user.must_change_password) {
            window.location.href = "change-password.html";
            return null;
        }

        if (session.user.role !== "manager") {
            routeUser(session);
            return null;
        }

        const allowedDomains = [
            "transport",
            "energy",
            "lpg",
            "water",
            "outreach"
        ];

        if (!allowedDomains.includes(session.user.manager_domain)) {
            throw new Error(
                "Manager account does not have a valid operational domain."
            );
        }

        return session;

    } catch (error) {
        window.location.href = "login.html";
        return null;
    }
}