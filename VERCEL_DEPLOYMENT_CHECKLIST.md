# 🔧 VERCEL DEPLOYMENT - Final Checklist

## ✅ Modifiche Pushate su GitHub

```bash
✅ 87d0c62 - Fix: Prioritize REST API for web apps (Vercel fix)
✅ 6378471 - feat: Add auth endpoints, template serving & smart URL resolution
✅ 18888f7 - Fix: Force Railway to use pip (nixpacks config)
```

---

## 🎯 Problema Risolto

**PRIMA**: Vercel provava ad usare PyWebView (desktop) anche su web
**ADESSO**: Vercel usa REST API come priorità assoluta

### Cambio Critico in `ui/app.js`

```javascript
async function api(name, payload) {
    // PRIMA: Provava PyWebView PRIMA di REST API
    // if (isDesktopApp()) { /* prova pywebview */ }
    // // poi REST API
    
    // ADESSO: Se web app, USA SEMPRE REST API
    if (isWebApp()) {
        // REST API direttamente ✅
        const apiBase = window.CooksyAPI.baseURL || 'https://cooksy-finaly.up.railway.app';
        const response = await fetch(`${apiBase}/api/${name}`, {...});
        return response.json();
    }
    // PyWebView solo se desktop
}
```

---

## 📋 Checklist Vercel Deployment

### 1️⃣ **Vercel Auto-Deploy** (dovrebbe partire automaticamente)

Vai: https://vercel.com/saveriodangelo-cyber/cooksy/deployments

Verifica:
- ✅ Nuovo deployment in corso (dopo push)
- ✅ Build completa senza errori
- ✅ Deploy status: "Ready"

### 2️⃣ **Configura Environment Variable**

https://vercel.com/saveriodangelo-cyber/cooksy/settings/environment-variables

Aggiungi (se non esiste):
```
Key: api_base_url
Value: https://cooksy-finaly.up.railway.app
Environments: Production, Preview, Development
```

Salva e **Redeploy** se necessario.

### 3️⃣ **Test Vercel URL**

Apri: https://cooksy.vercel.app (o tuo URL Vercel)

**F12 → Console** - Dovresti vedere:
```
[COOKSY] app.js loaded
[COOKSY] DOM ready
Cooksy API configured: https://cooksy-finaly.up.railway.app
```

**NO errori come**:
- ❌ "API webview2 not available"
- ❌ "pywebview is not defined"

### 4️⃣ **Test Autenticazione**

1. Click **"Registrati"**
2. Compila form:
   - Email: test@example.com
   - Password: Test123!
   - Username: testuser
3. Click **"Registrati"**

**F12 → Network Tab** - Verifica:
```
POST https://cooksy-finaly.up.railway.app/api/auth_register
Status: 201 Created
Response: {"ok": true, "user": {...}, "token": "..."}
```

**Header UI** - Dovresti vedere:
```
✅ Email: test@example.com
✅ Quota: (numero)
✅ Button "Esci" visible
```

### 5️⃣ **Test Template Caricamento**

Dropdown template dovrebbe:
- ✅ Popolarsi con ~30 template
- ✅ Mostrare nomi (Classico, Minimal, Design Moderno...)
- ✅ Click su un template → Preview carica

**F12 → Network Tab**:
```
GET https://cooksy-finaly.up.railway.app/api/templates
Status: 200 OK
Response: {"ok": true, "templates": [...], "count": 30}
```

### 6️⃣ **Test Upload File**

1. Click **"Seleziona file"**
2. Scegli un'immagine o PDF
3. Click **"Analizza"**

**F12 → Network Tab**:
```
POST https://cooksy-finaly.up.railway.app/api/upload
Status: 200 OK
```

---

## 🐛 Troubleshooting

### ❌ Ancora vedo "API webview2 not available"

**Causa**: Vercel non ha deployato ultimo commit

**Fix**:
```bash
# Verifica commit su GitHub
# https://github.com/saveriodangelo-cyber/Cooksy/commits/main

# Se commit manca, push di nuovo:
git push origin master:main --force

# Vai Vercel Dashboard → Redeploy
```

### ❌ "Unknown method: auth_login"

**Causa**: Railway non ha deployato backend nuovo

**Fix**:
```bash
# Test Railway:
curl -X POST https://cooksy-finaly.up.railway.app/api/auth_login \
  -H "Content-Type: application/json" \
  -d '{"email":"test","password":"test"}'

# Se ritorna "Unknown method" → Railway non deployato
# Vai Railway Dashboard → Trigger Manual Deploy
```

### ❌ Template dropdown vuoto

**Causa**: API `/api/templates` fallisce o non deployata

**Fix**:
```bash
# Test endpoint:
curl https://cooksy-finaly.up.railway.app/api/templates

# Dovrebbe ritornare: {"ok": true, "templates": [...], "count": 30}
```

### ❌ CORS Error

**Causa**: Railway blocca richieste da Vercel

**Verifica**: `backend/api_rest.py` deve avere:
```python
CORS(app, resources={r"/api/*": {"origins": "*"}})
```

Se hai cambiato a origins specifici, aggiungi:
```python
CORS(app, resources={r"/api/*": {"origins": [
    "https://cooksy.vercel.app",
    "https://*.vercel.app"
]}})
```

---

## ✅ Successo Finale

Vercel funziona quando:
- ✅ Console senza errori PyWebView
- ✅ Registrazione crea account
- ✅ Login mostra email in header
- ✅ Template dropdown popola (30 template)
- ✅ Upload file funziona
- ✅ Network tab mostra solo chiamate a Railway API

---

## 📞 Verifica Rapida (1 minuto)

```powershell
# Test che Railway backend funzioni
.\test-railway-deploy.ps1

# Dovrebbe mostrare:
# ✅ Backend is online
# ✅ Auth endpoint EXISTS
# ✅ Templates loaded: 30 templates
# ✅ Template HTML served
```

---

**Deployment completato!** Aspetta 2-3 minuti per auto-deploy Vercel, poi testa.
