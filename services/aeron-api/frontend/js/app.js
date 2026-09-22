document.addEventListener('DOMContentLoaded', () => {
    // Initialize Dashboard
    window.dashboard.init();

    // Simple navigation highlight logic
    const navLinks = document.querySelectorAll('.nav-links li');
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            navLinks.forEach(l => l.classList.remove('active'));
            link.classList.add('active');
        });
    });
});
