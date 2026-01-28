// Subscription/Stripe integration for UI
// Add to app.js after other event listeners

// Use 'el' function from app.js if available
const subEl = (id) => {
    if (typeof el === 'function') return el(id);
    return document.getElementById(id);
};

// Use 'showToast' from app.js if available
const subToast = (msg, type) => {
    if (typeof showToast === 'function') return showToast(msg, type);
    console.log(`[${type}] ${msg}`);
};

// Use 'apiReady' and 'api' from app.js
const subApiReady = () => {
    if (typeof apiReady === 'function') return apiReady();
    return window.pywebview && window.pywebview.api;
};

const subApi = async (method, payload) => {
    if (typeof api === 'function') return api(method, payload);
    if (!subApiReady()) return { ok: false, error: 'API non pronta' };
    try {
        return await window.pywebview.api[method](payload || {});
    } catch (e) {
        return { ok: false, error: String(e) };
    }
};

function initSubscriptionUI() {
    rebindSubscriptionListeners();
}

function rebindSubscriptionListeners() {
    const btnSubscription = subEl('btnSubscription');
    const subscriptionBackdrop = subEl('subscriptionBackdrop');
    const btnSubscriptionClose = subEl('btnSubscriptionClose');

    if (btnSubscription) {
        btnSubscription.addEventListener('click', showSubscriptionModal);
    }

    if (subscriptionBackdrop) {
        subscriptionBackdrop.addEventListener('click', hideSubscriptionModal);
    }

    if (btnSubscriptionClose) {
        btnSubscriptionClose.addEventListener('click', hideSubscriptionModal);
    }

    // Tier selection buttons
    ['btnTierFree', 'btnTierPro', 'btnTierBusiness'].forEach(id => {
        const btn = subEl(id);
        if (btn) {
            btn.addEventListener('click', (e) => {
                const tier = btn.id.replace('btnTier', '').toLowerCase();
                selectTier(tier);
            });
        }
    });

    // Invoice and payment history
    const btnDownloadInvoice = subEl('btnDownloadInvoice');
    if (btnDownloadInvoice) {
        btnDownloadInvoice.addEventListener('click', downloadInvoice);
    }

    const btnPaymentHistory = subEl('btnPaymentHistory');
    if (btnPaymentHistory) {
        btnPaymentHistory.addEventListener('click', showPaymentHistory);
    }
}

async function showSubscriptionModal() {
    const subscriptionModal = subEl('subscriptionModal');
    if (!subscriptionModal) return;

    subscriptionModal.classList.remove('hidden');
    subscriptionModal.setAttribute('aria-hidden', 'false');

    // Load current subscription data
    await loadSubscriptionData();
}

function hideSubscriptionModal() {
    const subscriptionModal = subEl('subscriptionModal');
    if (!subscriptionModal) return;
    subscriptionModal.classList.add('hidden');
    subscriptionModal.setAttribute('aria-hidden', 'true');
}

async function loadSubscriptionData() {
    if (!subApiReady() || (typeof authState !== 'undefined' && !authState.user)) {
        subToast('Effettua login per visualizzare abbonamento', 'error');
        return;
    }

    try {
        // Get current tier
        const tierRes = await subApi('get_subscription_status', {});
        if (tierRes?.ok) {
            const status = tierRes.subscription_id || tierRes.status || 'none';
            const tier = tierRes.tier || 'free';
            updateTierDisplay(tier, status);
        }

        // Get pricing
        const pricingRes = await subApi('get_tier_pricing', {});
        if (pricingRes?.ok) {
            updateTierPricing(pricingRes.tiers);
        }
    } catch (e) {
        console.error('Error loading subscription:', e);
    }
}

function updateTierDisplay(tier, status) {
    const tierName = subEl('tierName');
    const tierPrice = subEl('tierPrice');
    const tierFeature = subEl('tierFeature');

    const tiers = {
        free: { name: 'Free', price: 'Gratuito', feature: '3 ricette/mese' },
        pro: { name: 'Pro', price: '€9.99/mese', feature: '100 ricette/mese' },
        business: { name: 'Business', price: '€29.99/mese', feature: '500 ricette/mese' }
    };

    const tierData = tiers[tier] || tiers.free;
    if (tierName) tierName.textContent = tierData.name;
    if (tierPrice) tierPrice.textContent = tierData.price;
    if (tierFeature) tierFeature.textContent = tierData.feature;
}

function updateTierPricing(tiers) {
    if (!tiers) return;

    // Update tier options display
    ['free', 'pro', 'business'].forEach(tier => {
        const tierData = tiers[tier];
        if (!tierData) return;

        const opt = subEl(`tierOption_${tier}`);
        if (opt) {
            const name = opt.querySelector('.tierOptionName');
            const price = opt.querySelector('.tierOptionPrice');
            const desc = opt.querySelector('.tierOptionDesc');

            if (name) name.textContent = tierData.name;
            if (price) price.textContent = tierData.price ? `€${tierData.price}/mese` : 'Gratuito';
            if (desc) desc.textContent = tierData.description;
        }
    });
}

async function selectTier(tier) {
    const authStateRef = (typeof authState !== 'undefined') ? authState : null;
    if (!authStateRef || !authStateRef.user) {
        subToast('Effettua login per aggiornare abbonamento', 'error');
        if (typeof showAuthModal === 'function') {
            showAuthModal('login');
        }
        return;
    }

    if (tier === 'free') {
        // Cancel subscription
        if (confirm('Sei sicuro? Passerai a Free con 3 ricette/mese')) {
            const res = await subApi('cancel_subscription', {});
            if (res?.ok) {
                subToast('Abbonamento cancellato. Sei tornato a Free.', 'success');
                if (typeof updateAuthUi === 'function') {
                    updateAuthUi();
                }
                hideSubscriptionModal();
            } else {
                subToast(res?.error || 'Errore cancellazione abbonamento', 'error');
            }
        }
        return;
    }

    // Pro or Business: create checkout session
    subToast('Avvio pagamento Stripe...', 'info');

    // Get user email from auth state
    const userEmail = authStateRef.user?.email || '';
    const userId = authStateRef.user?.id || '';

    console.log('[Subscription] Creating checkout session for tier:', tier, 'email:', userEmail, 'user_id:', userId);

    const res = await subApi('create_checkout_session', {
        tier,
        email: userEmail,
        user_id: userId
    });

    console.log('[Subscription] Checkout response:', res);

    if (res?.ok && res.checkout_url) {
        // Open Stripe checkout in external browser
        subToast('Apertura pagamento in browser esterno...', 'success');

        // Use pywebview to open external browser
        if (window.pywebview && window.pywebview.api && window.pywebview.api.open_external_browser) {
            try {
                await window.pywebview.api.open_external_browser({ url: res.checkout_url });
            } catch (e) {
                console.error('Error opening external browser:', e);
                // Fallback: copy URL to clipboard
                if (navigator.clipboard) {
                    await navigator.clipboard.writeText(res.checkout_url);
                    subToast('URL pagamento copiato negli appunti. Incolla in un browser.', 'info');
                } else {
                    alert('Apri questo link per completare il pagamento:\n\n' + res.checkout_url);
                }
            }
        } else {
            // Fallback: show URL
            if (navigator.clipboard) {
                await navigator.clipboard.writeText(res.checkout_url);
                subToast('URL pagamento copiato negli appunti. Incolla in un browser.', 'info');
            } else {
                alert('Apri questo link per completare il pagamento:\n\n' + res.checkout_url);
            }
        }
    } else {
        subToast(res?.error || 'Errore creazione sessione pagamento', 'error');
        console.error('[Subscription] Error:', res?.error);
    }
}

async function downloadInvoice() {
    subToast('Download fattura in sviluppo', 'info');
    // TODO: Implement invoice download
}

async function showPaymentHistory() {
    subToast('Storico pagamenti in sviluppo', 'info');
    // TODO: Implement payment history modal
}

// Remove DOMContentLoaded listener - initSubscriptionUI will be called from app.js
