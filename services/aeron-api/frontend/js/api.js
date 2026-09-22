const API_BASE_URL = '/api/environment';

class ApiService {
    async fetchLatestWeather() {
        try {
            const response = await fetch(`${API_BASE_URL}/latest`);
            if (!response.ok) throw new Error('Weather data fetch failed');
            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            return null;
        }
    }

    async fetchLatestAQI() {
        try {
            const response = await fetch(`${API_BASE_URL}/latest`);
            if (!response.ok) throw new Error('AQI data fetch failed');
            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            return null;
        }
    }

    async fetchHistory(type) {
        try {
            const response = await fetch(`${API_BASE_URL}/history?limit=24`);
            if (!response.ok) throw new Error(`History fetch failed for ${type}`);
            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            return [];
        }
    }

}

window.apiService = new ApiService();
