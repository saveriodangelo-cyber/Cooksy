# 🚀 Cooksy: Quick Start Monetizzazione

Guida rapida per avviare Cooksy e iniziare a guadagnare in **3 ore**.

## ⚡ TL;DR (3 passi)

```bash
# 1. Deploy backend su Render (2 min)
# - Vai https://render.com → Create Web Service
# - Connetti GitHub repo
# - Start: python -m backend.api_rest

# 2. Deploy frontend su Vercel (2 min)
# - Vai https://vercel.com → Import Project
# - Seleziona cartella ui/

# 3. Setup Stripe (5 min)
# - Crea dashboard.stripe.com
# - Copia STRIPE_SECRET_KEY
# - Aggiungilo a Render environment
```

**Risultato**: App live su web + mobile, pronta a vendere via Stripe.

---

## 📱 Step 1: Test Locale (15 min)

### Setup

```bash
cd c:\Users\saver\OneDrive\Progetti\ricetta

# Installa dipendenze
pip install -r requirements.txt

# Avvia API
python -m backend.api_rest
# Ascolta su http://localhost:5000
```

### Test API

```bash
# In altro terminal:
curl http://localhost:5000/api/health
# Risposta: {"status": "ok", "service": "cooksy-api"}

curl http://localhost:5000/api/templates
# Mostra lista template HTML
```

---

## ☁️ Step 2: Deploy Backend su Render.com (GRATIS)

### 2.1 Setup Account Render

1. Vai https://render.com
2. Sign up con GitHub
3. Autorizza render per accedere ai tuoi repo

### 2.2 Crea Web Service

1. Dashboard Render → **New** → **Web Service**
2. Seleziona repository `ricetta`
3. Configurazione:
   ```
   Name: cooksy-api
   Runtime: Python 3.11
   Build: pip install -r requirements.txt
   Start: python -m backend.api_rest
   Region: Europe (Frankfurt)
   Plan: Free ($0/mese, sleep dopo 15 min inattivita)
   ```

4. **Environment Variables** (premi Add):
   ```
   FLASK_ENV = production
   FLASK_DEBUG = 0
   STRIPE_SECRET_KEY = sk_test_... (dalla tua Stripe)
   STRIPE_PUBLISHABLE_KEY = pk_test_...
   ```

5. Clicca **Create Web Service**

**⏱ Tempo**: ~2 minuti. App sarà live su `https://cooksy-api-XXX.onrender.com`

### 2.3 Verifica Deploy

```bash
curl https://cooksy-api-XXX.onrender.com/api/health
# {"status": "ok", "service": "cooksy-api"}
```

---

## 🌐 Step 3: Deploy Frontend su Vercel (GRATIS)

### 3.1 Setup Vercel

1. Vai https://vercel.com
2. Sign up con GitHub
3. Autorizza Vercel

### 3.2 Deploy

1. **Add New** → **Project** → Seleziona repo `ricetta`
2. Configurazione:
   ```
   Framework: Other
   Build Command: (lascia vuoto)
   Output Directory: ui/
   Root Directory: ui/
   ```

3. **Environment Variables**:
   ```
   REACT_APP_API_URL = https://cooksy-api-XXX.onrender.com
   ```

4. Clicca **Deploy**

**⏱ Tempo**: ~1 minuto. Live su `cooksy.vercel.app`

---

## 💳 Step 4: Setup Stripe (MONETIZZAZIONE)

### 4.1 Crea Account Stripe

1. Vai https://dashboard.stripe.com/register
2. Email + password
3. Attiva Live Mode quando pronto

### 4.2 Prendi API Keys

1. Dashboard Stripe → **API Keys**
2. Copia:
   - `Secret Key` (sk_live_...)
   - `Publishable Key` (pk_live_...)

### 4.3 Aggiorna Render

1. Dashboard Render → cooksy-api → **Environment**
2. Aggiorna `STRIPE_SECRET_KEY` con chiave **live**
3. Aggiorna `STRIPE_PUBLISHABLE_KEY`
4. Redeploy

### 4.4 Test Pagamento

Testa con [numeri carta Stripe](https://stripe.com/docs/testing):
```
Numero: 4242 4242 4242 4242
Scadenza: 12/25
CVC: 123
```

---

## 💰 Pricing Strategy

### Opzione 1: Web PWA (0% commissione store)

- Accedi da `cooksy.vercel.app`
- Abbonamenti via Stripe
- **Revenue**: 100% - 2.9% Stripe - €0.30/transazione

**Margine**: ~97% su ogni vendita

### Opzione 2: Google Play (15% commissione)

- Compila APK da `build-deploy.bat build-apk`
- Carica su Google Play ($25 una volta)
- Setup In-App Purchase
- **Revenue**: 85% - 2.9% Stripe - €0.30/transazione

**Margine**: ~82% su ogni vendita

### Opzione 3: App Store iOS (30% commissione)

- Necessario: Mac + Apple Developer ($99/anno)
- Build IPA da XCode
- Submit su App Store
- **Revenue**: 70% - 2.9% Stripe - €0.30/transazione

**Margine**: ~67% su ogni vendita

---

## 📊 Pricing Suggerito

| Tier | Prezzo | Uso | Margine |
|------|--------|-----|--------|
| Free | Gratis | Test 5 ricette/mese | - |
| Starter | €4.99/mese | 100 ricette + esport PDF | €4.84 |
| Pro | €9.99/mese | Illimitato + archivio | €9.70 |
| Business | €19.99/mese | Team + API | €19.41 |

**Conversione attesa**: 5-10% dei free users

---

## 🔐 Security Checklist

- ✅ API su HTTPS (Render automatic)
- ✅ Frontend su HTTPS (Vercel automatic)
- ✅ Stripe webhook verification
- ✅ Rate limiting
- ✅ CORS limited
- ✅ Secrets in environment variables (not in code)

---

## 📈 Monitoring

### Render Dashboard
- CPU/Memory usage
- Deploy logs
- Error tracking

### Vercel Analytics
- Page speed
- Core Web Vitals
- Deployment history

### Stripe Dashboard
- Transazioni
- Revenue
- Refunds

---

## 🆘 Troubleshooting

### API non risponde
```bash
# Check Render logs
# Dashboard → cooksy-api → Logs
# Cerca "Starting Cooksy API"
```

### Frontend non carica
```bash
# Check Vercel deployment
# Settings → Deployments → Vedi logs
# Controlla CORS errors in console
```

### Pagamenti non funzionano
```bash
# Stripe test mode? (sk_test_... vs sk_live_...)
# Webhook registrato?
# Rate limits?
```

---

## 📞 Costi Mensili Reali

| Servizio | Tier | Costo | Note |
|----------|------|-------|------|
| Render (Backend) | Free | €0 | Sleep 15 min |
| Vercel (Frontend) | Free | €0 | Unlimited bandwidth |
| Stripe | Payment processor | 2.9% + €0.30 | Solo su vendite |
| Dominio | Facoltativamente | €10-20/anno | cooksy.app |
| **TOTALE** | | **€0-2** | Scalabile a richiesta |

---

## 🎯 Prossimi Step

1. **T+30 min**: Tutti i servizi live
2. **T+60 min**: Test pagamenti funzionano
3. **T+90 min**: Annuncia beta agli amici
4. **T+180 min**: Primo revenue! 🎉

---

## 📚 Link Utili

- [Render Docs](https://render.com/docs)
- [Vercel Docs](https://vercel.com/docs)
- [Stripe API](https://stripe.com/docs/api)
- [Flask Docs](https://flask.palletsprojects.com/)

---

**Domande?** Apri Issue su GitHub o contatta support Render/Vercel/Stripe.

**Buona fortuna!** 🚀
