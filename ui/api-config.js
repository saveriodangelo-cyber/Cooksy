// Configurazione API per production
const API_BASE_URL = 'https://cooksy-finaly.up.railway.app';

// Helper per chiamate API
async function apiCall(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const response = await fetch(url, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options.headers
        }
    });
    return response.json();
}

// Export per usarlo nel frontend
window.CooksyAPI = {
    baseURL: API_BASE_URL,

    // Health check
    async checkHealth() {
        return apiCall('/api/health');
    },

    // Lista template
    async getTemplates() {
        return apiCall('/api/templates');
    },

    // Upload file
    async uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(`${API_BASE_URL}/api/upload`, {
            method: 'POST',
            body: formData
        });
        return response.json();
    },

    // Status
    async getStatus() {
        return apiCall('/api/status');
    }
};

console.log('Cooksy API configured:', API_BASE_URL);
