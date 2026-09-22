(function () {
    const form = document.getElementById("login-form");
    if (!form) return;

    const role = document.body.dataset.loginRole;
    const domain = document.body.dataset.loginDomain || null;
    const destination = document.body.dataset.destination;
    const message = document.getElementById("login-message");
    const submitButton = form.querySelector('button[type="submit"]');

    function showMessage(text) {
        message.textContent = text;
    }

    async function handleSession(session, fromLogin) {
        const user = session?.user;

        if (!KCosmosAuth.isExpectedUser(user, role, domain)) {
            if (fromLogin) {
                try {
                    await logout();
                } catch (_) {
                    /* reject the mismatched session locally */
                }
            }

            showMessage("This account is not authorized for this portal.");
            return;
        }

        if (user.must_change_password) {
            window.location.replace("change-password.html");
            return;
        }

        window.location.replace(destination);
    }

    form.addEventListener("submit", async event => {
        event.preventDefault();

        submitButton.disabled = true;
        showMessage("Signing in...");

        try {
            const session = await login(
                document.getElementById("login-username").value.trim(),
                document.getElementById("login-password").value
            );

            document.getElementById("login-password").value = "";

            await handleSession(session, true);
        } catch (error) {
            document.getElementById("login-password").value = "";
            showMessage(error.message);
        } finally {
            submitButton.disabled = false;
        }
    });

    getSession()
        .then(session => handleSession(session, false))
        .catch(() => {});
})();
