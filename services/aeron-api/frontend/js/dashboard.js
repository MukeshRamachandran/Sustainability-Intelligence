class DashboardController {
    constructor() {
        this.api = window.apiService;
        this.charts = window.charts;
        this.updateInterval = null;
    }

    async init() {
        this.updateDateTime();
        setInterval(() => this.updateDateTime(), 1000);

        await this.loadData();
        
        // Refresh data every minute
        this.updateInterval = setInterval(() => this.loadData(), 60000);
    }

    updateDateTime() {
        const now = new Date();
        const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' };
        document.getElementById('current-datetime').textContent = now.toLocaleDateString('en-US', options);
    }

    async loadData() {
        this.setLoadingState(true);
        try {
            const [weather, aqi, weatherHistory, aqiHistory] = await Promise.all([
                this.api.fetchLatestWeather(),
                this.api.fetchLatestAQI(),
                this.api.fetchHistory('weather'),
                this.api.fetchHistory('air-quality')
            ]);

            this.updateKPIs(weather, aqi);
            
            // Initialize charts if not already done
            if (!this.charts.aqiChart) {
                this.charts.initAQIChart(aqiHistory);
                this.charts.initWeatherChart(weatherHistory);
            } else {
                this.charts.updateCharts(aqiHistory, weatherHistory);
            }

            this.updateApiStatus('Live', 'success');
        } catch (error) {
            console.error('Failed to load dashboard data:', error);
            this.updateApiStatus('Error', 'danger');
        } finally {
            this.setLoadingState(false);
        }
    }

    updateKPIs(weather, aqi) {
        // AQI
        const aqiEl = document.getElementById('kpi-aqi');
        const aqiStatus = document.getElementById('kpi-aqi-status');
        if (aqi.aqi) {
            aqiEl.textContent = Math.round(aqi.aqi);
            const status = this.getAQIStatus(aqi.aqi);
            aqiStatus.textContent = status.text;
            aqiStatus.style.color = status.color;
        }

        // PM2.5
        if (aqi.pm25) {
            document.getElementById('kpi-pm25').textContent = aqi.pm25.toFixed(1);
        }

        // Temperature
        if (weather.temperature) {
            document.getElementById('kpi-temp').textContent = weather.temperature.toFixed(1);
            // Mock feels like
            document.getElementById('kpi-feels-like').textContent = (weather.temperature + 1).toFixed(1) + '°C';
        }

        // Humidity
        if (weather.humidity) {
            document.getElementById('kpi-humidity').textContent = weather.humidity.toFixed(1);
            // Mock dew point
            document.getElementById('kpi-dew-point').textContent = (weather.temperature - 5).toFixed(1) + '°C';
        }
    }

    getAQIStatus(value) {
        if (value <= 50) return { text: 'Good', color: 'var(--success)' };
        if (value <= 100) return { text: 'Moderate', color: 'var(--warning)' };
        return { text: 'Unhealthy', color: 'var(--danger)' };
    }

    setLoadingState(isLoading) {
        // Optional: add loading spinner logic here
    }

    updateApiStatus(text, type) {
        const statusEl = document.getElementById('api-status');
        const dot = document.querySelector('.pulse-dot');
        statusEl.textContent = text;
        
        if (type === 'danger') {
            dot.style.background = 'var(--danger)';
            dot.style.boxShadow = '0 0 0 0 rgba(239, 68, 68, 0.7)';
        } else {
            dot.style.background = 'var(--success)';
            dot.style.boxShadow = '0 0 0 0 rgba(16, 185, 129, 0.7)';
        }
    }
}

window.dashboard = new DashboardController();
