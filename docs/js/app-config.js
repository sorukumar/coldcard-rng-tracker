document.addEventListener('DOMContentLoaded', () => {
    if (typeof BitcoinLabsApp !== 'undefined') {
        BitcoinLabsApp.init({
            isApp: true,
            appName: 'coldcard-rng-tracker',
            appHomeUrl: 'index.html',
            navLinks: [
                { name: 'Dashboard', url: 'index.html', icon: 'fas fa-chart-pie' },
                { name: 'Graph Explorer', url: 'explorer.html', icon: 'fas fa-project-diagram' },
                { name: 'How We Track', url: 'methodology.html', icon: 'fas fa-book-open' }
            ],
            suiteLinks: [] // Pass empty array to prevent defaults
        });

        // Force the body to have the 'has-nav' class for mobile hamburger menu
        document.body.classList.add('has-nav');

    }
});
