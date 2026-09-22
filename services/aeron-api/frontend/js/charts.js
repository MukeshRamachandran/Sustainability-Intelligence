Chart.defaults.color = '#94A3B8';
Chart.defaults.font.family = "'Outfit', sans-serif";

class DashboardCharts {
    constructor() {
        this.aqiChart = null;
        this.weatherChart = null;
    }

    initAQIChart(data) {
        const ctx = document.getElementById('aqiChart').getContext('2d');
        
        // Setup gradients
        const gradient = ctx.createLinearGradient(0, 0, 0, 400);
        gradient.addColorStop(0, 'rgba(59, 130, 246, 0.5)');
        gradient.addColorStop(1, 'rgba(59, 130, 246, 0.0)');

        const labels = data.map(d => new Date(d.timestamp).getHours() + ':00').reverse();
        const aqiValues = data.map(d => d.aqi).reverse();

        this.aqiChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'AQI Index',
                    data: aqiValues,
                    borderColor: '#3B82F6',
                    backgroundColor: gradient,
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        backgroundColor: 'rgba(15, 23, 42, 0.9)',
                        titleColor: '#F8FAFC',
                        bodyColor: '#94A3B8',
                        borderColor: 'rgba(255,255,255,0.1)',
                        borderWidth: 1
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(255,255,255,0.05)' }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    }

    initWeatherChart(data) {
        const ctx = document.getElementById('weatherChart').getContext('2d');
        
        const labels = data.map(d => new Date(d.timestamp).getHours() + ':00').reverse();
        const tempValues = data.map(d => d.temperature).reverse();
        const humidityValues = data.map(d => d.humidity).reverse();

        this.weatherChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Temperature (°C)',
                        data: tempValues,
                        borderColor: '#F59E0B',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        tension: 0.4,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Humidity (%)',
                        data: humidityValues,
                        borderColor: '#10B981',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        tension: 0.4,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        grid: { color: 'rgba(255,255,255,0.05)' }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        grid: { drawOnChartArea: false }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    }

    updateCharts(aqiData, weatherData) {
        if (!this.aqiChart || !this.weatherChart) return;
        
        // Update logic would go here in a real scenario
        // e.g. this.aqiChart.data.datasets[0].data = ...
        // this.aqiChart.update();
    }
}

window.charts = new DashboardCharts();
