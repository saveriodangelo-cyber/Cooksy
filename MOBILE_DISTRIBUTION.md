# 📱 Guida Distribuzione Cooksy su Android/iOS - PWA + Mobile

Questo documento spiega come distribuire Cooksy su Android, iOS e web in modo **gratuito e veloce**.

## 🎯 Architettura

```
┌─────────────────────────────────────────────────────┐
│  CLIENT (Web + PWA + Capacitor)                     │
│  - HTML/CSS/JS (ui/)                                │
│  - Service Worker (caching offline)                 │
│  - Android APK (via Capacitor)                      │
│  - iOS IPA (via Capacitor + XCode)                  │
└──────────┬──────────────────────────────────────────┘
           │ API REST HTTP
           │ https://api.cooksy.app/api/*
           │
┌──────────┴──────────────────────────────────────────┐
│  BACKEND (Python + Flask)                           │
│  - Backend API (http://localhost:5000)              │
│  - OCR + Parsing + IA                               │
│  - PDF/DOCX Export                                  │
│  - Database SQLite                                  │
└─────────────────────────────────────────────────────┘
```

---

## 🚀 PASSO 1: Setup Backend API

### 1.1 Installare dipendenze
```bash
pip install Flask Flask-CORS
```

### 1.2 Avviare API localmente (test)
```bash
cd /path/to/ricetta
python -m backend.api_rest
# Server parte su http://localhost:5000
```

Testa endpoint:
```bash
curl http://localhost:5000/api/health
# Risposta: {"status": "ok", "service": "cooksy-api"}
```

---

## ☁️ PASSO 2: Deploy Backend su Cloud (Render/Railway) - GRATIS

### Opzione A: Render.com (CONSIGLIATO)

1. **Vai su** https://render.com e registrati (gratis)

2. **Crea nuovo Web Service**:
   - Collega il tuo GitHub repo
   - Branch: `main` (o il tuo branch)
   - Build command: `pip install -r requirements.txt`
   - Start command: `python -m backend.api_rest`
   - Environment: Python 3.11
   - Plan: Free (0.5 CPU, 0.5 GB RAM)

3. **Aggiungi environment variables** (dal dashboard Render):
   ```
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_PUBLISHABLE_KEY=pk_test_...
   RICETTEPDF_OLLAMA_URL=http://ollama:11434
   RICETTEPDF_MODEL=mistral
   RICETTEPDF_TIMEOUT_S=120
   FLASK_ENV=production
   ```

4. **Deploy**: Render auto-deploy ad ogni git push

⚠️ **Limitazioni tier free Render**:
- Va in sleep dopo 15 min inattività
- Wake-up time ~30 sec
- CPU limitata
- Perfetto per testing/produzione leggera

### Opzione B: Railway.app

1. **Vai su** https://railway.app e registrati (connetti GitHub)

2. **New Project → GitHub Repo**:
   - Rileva automaticamente Dockerfile + railway.json
   - Deploy auto

3. **Environment → Add Variable**: Aggiungi stesse env di Render

Entrambi offrono **$5/mese free tier** (sufficiente per versione beta).

---

## 🌐 PASSO 3: Setup Frontend Web (PWA)

I file richiesti sono già stati creati:
- ✅ `ui/manifest.json` - PWA metadata
- ✅ `ui/service-worker.js` - Offline + caching
- ✅ `ui/offline.html` - Pagina offline
- ✅ `ui/index.html` - link manifest + meta PWA

### 3.1 Aggiorna API endpoint in app.js

Modifica il file `ui/app.js` per usare l'API REST remota:

```javascript
// Aggiungi all'inizio di app.js (o in una funzione di config):
const API_BASE = process.env.NODE_ENV === 'production'
  ? 'https://api.cooksy.app'  // URL pubblico Render/Railway
  : 'http://localhost:5000';   // Locale per testing

// Ovunque calls bridge, converti a fetch:
// DA:
//   window.api.analyze_start(files, options)
// A:
//   fetch(`${API_BASE}/api/analyze/start`, {
//     method: 'POST',
//     headers: { 'Content-Type': 'application/json' },
//     body: JSON.stringify({ file_paths: files, ai_options: options })
//   }).then(r => r.json())
```

### 3.2 Deploy web su CDN gratis

Scegli uno (tutti gratuiti):

#### Opzione 1: **Vercel** (CONSIGLIATO per Next.js)
```bash
npm i -g vercel
cd /path/to/ricetta/ui
vercel --prod
```

#### Opzione 2: **Netlify**
```bash
npm i -g netlify-cli
cd /path/to/ricetta/ui
netlify deploy --prod
```

#### Opzione 3: **GitHub Pages** (+ GitHub Actions)
- Crea file `.github/workflows/deploy.yml`:

```yaml
name: Deploy Web
on:
  push:
    branches: [main]
    paths: ['ui/**']

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to GitHub Pages
        run: |
          mkdir -p dist
          cp -r ui/* dist/
          echo "cooksy.app" > dist/CNAME
      - uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./dist
```

---

## 📱 PASSO 4: Convertire Web → Android APK (Capacitor)

### 4.1 Setup Capacitor

```bash
# Installa Capacitor
npm init
npm install -D @capacitor/core @capacitor/cli

# Inizializza app Capacitor
npx cap init cooksy "Cooksy" --web-dir=ui/

# Aggiungi platform Android
npx cap add android
```

### 4.2 Configura Capacitor (capacitor.config.json)

```json
{
  "appId": "com.cooksy.app",
  "appName": "Cooksy",
  "webDir": "ui",
  "server": {
    "url": "https://api.cooksy.app"
  },
  "plugins": {
    "Camera": {
      "permissions": ["CAMERA"]
    },
    "Filesystem": {}
  }
}
```

### 4.3 Build APK

```bash
# Build Android
npx cap build android

# Oppure manuale:
cd android && ./gradlew assembleRelease
# APK: android/app/build/outputs/apk/release/app-release.apk
```

**Alternativa senza Capacitor**: Installa come Progressive Web App direttamente:
- Android: Apri su Chrome → Menu → "Installa app"
- iOS: Safari → Share → "Aggiungi a Home"

---

## 🍎 PASSO 5: iOS (Opzione)

### Se non hai Mac:
- **EAS Build** (Expo) per compilare online
- **PWA su Safari** (no app store)

### Se hai Mac:
```bash
npx cap add ios
npx cap open ios
# Apri in XCode, firma con Apple Developer cert, build
```

---

## 💰 MONETIZZAZIONE

### Stripe Integration (già configurato)

1. **Web/PWA**: Pulsante "Upgrade" → Checkout Stripe
   ```javascript
   const response = await fetch(`${API_BASE}/api/checkout`, {
     method: 'POST',
     body: JSON.stringify({ tier: 'pro', user_id: ... })
   });
   window.location.href = response.checkout_url;
   ```

2. **App Store** (per iOS):
   - Apple richiede In-App Purchase (30% commissione)
   - Integra con Stripe → webhook sincronizza su app

3. **Google Play** (per Android):
   - Free upload (15% commissione con Google Play Billing)
   - Oppure: APK diretto dal sito (nessuna commissione)

**Strategia consigliata**:
- **Beta**: APK gratis diretto da sito
- **Produzione**: Google Play + App Store per credibilità
- **Revenue**: Stripe per web + In-App Purchase su store

---

## 📊 Costi Mensili (stima)

| Componente | Costo | Note |
|------------|-------|------|
| API Backend (Render free tier) | €0 | 1 istanza, sleep dopo 15 min |
| CDN Frontend (Vercel/Netlify) | €0 | Unlimited bandwidth gratuito |
| Database (SQLite) | €0 | Incluso nel backend |
| Stripe | 2.9% + €0.30/transazione | Solo su vendite |
| Dominio | €0-10 | Gratis .app via GitHub Pages |
| **TOTALE** | **€0-10** | Scalabile a pagamento |

---

## 🧪 Testing pre-deploy

```bash
# 1. Test API locale
python -m backend.api_rest &
curl http://localhost:5000/api/health

# 2. Test PWA locale
cd ui && python -m http.server 8000
# Apri http://localhost:8000 → Ctrl+Shift+I → Console
# Controlla: Service Worker registered

# 3. Test Mobile (Android emulator)
emulator -avd MyEmulator &
npx cap open android
# Build in Android Studio
```

---

## 🔐 Security Checklist

- ✅ HTTPS solo (Render/Railway/Vercel automatico)
- ✅ CORS limited a domini tuoi
- ✅ API rate limiting (aggiungere limits.py)
- ✅ Stripe webhook signature verification
- ✅ JWT tokens per autenticazione
- ✅ CSRF token in manifest
- ✅ Content-Security-Policy headers

---

## 📞 Support Deploy

**Render docs**: https://render.com/docs  
**Capacitor docs**: https://capacitorjs.com/docs  
**PWA guide**: https://web.dev/progressive-web-apps/

---

**Prossimi passi**:
1. Push code a GitHub
2. Connetti Render/Railway
3. Deploy API
4. Deploy frontend (Vercel/Netlify)
5. Test APK su emulator Android
6. Pubblica su Google Play / TestFlight

Entro **3-4 ore** di lavoro: **Cooksy live su web + Android + iOS!** 🎉
