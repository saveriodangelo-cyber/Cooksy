/**
 * Service Worker per Cooksy PWA
 * Gestisce caching, offline, push notifications
 */

const CACHE_NAME = 'cooksy-v1';
const API_CACHE = 'cooksy-api-v1';
const OFFLINE_PAGE = '/offline.html';

const urlsToCache = [
    '/',
    '/index.html',
    '/style.css',
    '/app.js',
    '/subscription_ui.js',
    '/assets/logo-192x192.png',
    '/assets/logo-512x512.png',
];

// Install: cache static assets
self.addEventListener('install', (event) => {
    console.log('[SW] Installing...');
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('[SW] Caching app shell');
                return cache.addAll(urlsToCache);
            })
            .then(() => self.skipWaiting())
    );
});

// Activate: cleanup old caches
self.addEventListener('activate', (event) => {
    console.log('[SW] Activating...');
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME && cacheName !== API_CACHE) {
                        console.log('[SW] Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// Fetch: network-first per API, cache-first per assets
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);

    // Skip non-GET
    if (request.method !== 'GET') {
        return;
    }

    // API calls: network-first, fallback to offline
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(request)
                .then((response) => {
                    if (!response || response.status !== 200 || response.type !== 'basic') {
                        return response;
                    }
                    const responseToCache = response.clone();
                    caches.open(API_CACHE).then((cache) => {
                        cache.put(request, responseToCache);
                    });
                    return response;
                })
                .catch(() => {
                    // Offline fallback
                    return caches.match(request)
                        .then((response) => {
                            return response || caches.match(OFFLINE_PAGE);
                        });
                })
        );
        return;
    }

    // Static assets: cache-first, fallback to network
    event.respondWith(
        caches.match(request)
            .then((response) => {
                if (response) {
                    return response;
                }
                return fetch(request)
                    .then((response) => {
                        if (!response || response.status !== 200 || response.type !== 'basic') {
                            return response;
                        }
                        const responseToCache = response.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(request, responseToCache);
                        });
                        return response;
                    })
                    .catch(() => {
                        return caches.match(OFFLINE_PAGE);
                    });
            })
    );
});

// Background sync: retry failed requests
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-recipes') {
        event.waitUntil(
            syncRecipes().catch(() => {
                console.log('[SW] Sync failed, will retry');
            })
        );
    }
});

async function syncRecipes() {
    const cache = await caches.open(API_CACHE);
    const requests = await cache.keys();

    const promises = requests.map((request) => {
        return fetch(request).then((response) => {
            if (response.ok) {
                cache.put(request, response);
            }
        });
    });

    await Promise.all(promises);
}

// Message from client
self.addEventListener('message', (event) => {
    if (event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});
