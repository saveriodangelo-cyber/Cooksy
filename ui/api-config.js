// Configurazione API per production
// Priorizzazione:
// 1. Se disponibile env variable (iniettata da Vercel)
// 2. Se stessa origine (Vercel, Railway server)
// 3. Fallback a Railway per compatibilità legacy

const API_BASE_URL = (() => {
    // Se disponibile via window config
    if (typeof window.COOKSY_API_URL !== 'undefined') {
        return window.COOKSY_API_URL;
    }

    // Se disponibile via env (Vercel injection)
    if (typeof process !== 'undefined' && process.env.REACT_APP_API_URL) {
        return process.env.REACT_APP_API_URL;
    }

    // Same origin (per deploy monolith su Railway)
    if (window.location.protocol === 'https:' || window.location.protocol === 'http:') {
        const origin = window.location.origin;
        // Se non è localhost/127.0.0.1, prova stessa origine prima di fallback
        if (!origin.includes('localhost') && !origin.includes('127.0.0.1')) {
            return origin;
        }
    }

    // Fallback a Railway (legacy)
    return 'https://cooksy-finaly.up.railway.app';
})();

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
