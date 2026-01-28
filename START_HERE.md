# 🎬 START HERE: 5 Passi per Iniziare

Segui questi 5 passi nell'ordine. **~20 minuti totali**.

---

## PASSO 1: Test Locale (5 min)

Verifica che tutto funziona sul tuo computer:

```bash
# Terminal PowerShell in ricetta/
.\start-dev.bat
```

Questo avvia:
- API su http://localhost:5000
- Frontend su http://localhost:8000
- Browser si apre automaticamente

**Verifica**:
- [ ] API health ok: http://localhost:5000/api/health
- [ ] Frontend carica: http://localhost:8000
- [ ] Nessun errore in console

---

## PASSO 2: GitHub Setup (2 min)

```bash
# Se non hai ancora git:
git init
git add .
git commit -m "Initial commit: Cooksy API + PWA"
git remote add origin https://github.com/TUO_USER/ricetta.git
git branch -M main
git push -u origin main
```

---

## PASSO 3: Deploy Backend (3 min)

### 3.1 Crea Account Render

Vai https://render.com → Sign up con GitHub

### 3.2 Crea Web Service

1. Dashboard → **New** → **Web Service**
2. Seleziona repo `ricetta`
3. Configurazione:
   ```
   Name: cooksy-api
   Runtime: Python 3.11
   Build: pip install -r requirements.txt
   Start: python -m backend.api_rest
   Region: Europe
   Plan: Free
   ```
4. **Create Web Service**

### 3.3 Aggiungi Environment Variables

1. Dopo il deploy → **Environment** → **Add Environment Variable**
2. Aggiungi:
   ```
   FLASK_ENV = production
   FLASK_DEBUG = 0
   ```
3. **Manual Deploy** per applicare

**Risultato**: API live su `https://cooksy-api-XXX.onrender.com`

Test:
```bash
curl https://cooksy-api-XXX.onrender.com/api/health
```

---

## PASSO 4: Deploy Frontend (3 min)

### 4.1 Crea Account Vercel

Vai https://vercel.com → Sign up con GitHub

### 4.2 Import Progetto

1. **Add New** → **Project**
2. Seleziona repo `ricetta`
3. Configurazione:
   ```
   Framework: Other (no framework)
   Build Command: (lascia vuoto)
   Output Directory: (lascia vuoto)
   Root Directory: ui/
   ```
4. **Deploy**

**Risultato**: Frontend live su `cooksy.vercel.app`

---

## PASSO 5: Setup Stripe (5 min)

### 5.1 Crea Account Stripe

Vai https://dashboard.stripe.com/register

### 5.2 Attiva Test Mode

Dashboard → Attiva modalità Test (toggle in alto a destra)

### 5.3 Prendi API Keys

1. Developers → API Keys
2. Copy:
   - Test Secret Key (sk_test_...)
   - Test Publishable Key (pk_test_...)

### 5.4 Aggiorna Render

1. Render Dashboard → cooksy-api → Environment
2. **Add Environment Variable**:
   ```
   STRIPE_SECRET_KEY = sk_test_...
   STRIPE_PUBLISHABLE_KEY = pk_test_...
   ```
3. **Manual Deploy**

### 5.5 Test Pagamento

Apri Vercel app → Prova con numero test:
```
Numero: 4242 4242 4242 4242
Scadenza: 12/25
CVC: 123
Postal: 12345
```

Controlla Stripe Dashboard → Payments per verificare la transazione.

---

## BONUS: Setup Auto-Deploy (2 min)

Così ogni volta che fai `git push`, il deploy avviene automaticamente.

### 6.1 GitHub Secrets

Vai: https://github.com/TUO_USER/ricetta/settings/secrets/actions

**New repository secret**:
```
RENDER_SERVICE_ID = (da Render → Settings → Internal ID)
RENDER_API_KEY = (da Render → Account → API Keys)
VERCEL_TOKEN = (da Vercel → Settings → Tokens)
VERCEL_ORG_ID = (da Vercel → Account)
VERCEL_PROJECT_ID = (da Vercel → Project Settings)
```

### 6.2 Test Auto-Deploy

```bash
# Modifica un file
echo "# Updated" >> QUICK_START.md

# Commit e push
git add .
git commit -m "Test auto-deploy"
git push origin main

# Controlla:
# - GitHub Actions: https://github.com/TUO_USER/ricetta/actions
# - Render deploy: https://dashboard.render.com/cooksy-api/timeline
# - Vercel deploy: https://vercel.com/deployments
```

---

## 📊 Checklist Finale

- [ ] Localhost funziona
- [ ] GitHub repo creato
- [ ] API live su Render
- [ ] Frontend live su Vercel
- [ ] Stripe test mode attivo
- [ ] Payment test OK
- [ ] Auto-deploy configurato

---

## 🔗 Link Utili

| Cosa | Link |
|------|------|
| Render Dashboard | https://dashboard.render.com |
| Vercel Dashboard | https://vercel.com |
| Stripe Dashboard | https://dashboard.stripe.com |
| GitHub Repo | https://github.com/TUO_USER/ricetta |
| Frontend Live | https://cooksy.vercel.app |
| API Live | https://cooksy-api-XXX.onrender.com |

---

## 💡 Next Steps

1. **Settimana 1**: Beta test con 10 amici
2. **Settimana 2**: Feedback, bugfix
3. **Settimana 3**: Pubblica su Google Play
4. **Settimana 4**: Attiva Stripe live mode
5. **Mese 2**: Revenue! 🎉

---

## 🆘 Se qualcosa non funziona

### API non parte
```bash
# Check logs Render
# Dashboard → Logs
# Cerca "Starting Cooksy API"
```

### Frontend non carica
```bash
# Check Vercel logs
# https://vercel.com/deployments
# Verifica CORS errors in console (F12)
```

### Stripe non funziona
```bash
# Sei in test mode? (sk_test_)
# Controlla Stripe webhook logs
# Prova numero di test: 4242 4242 4242 4242
```

---

**Fatto! Ora Cooksy è live e pronto a guadagnare.** 🚀

Quando sei pronto per la produzione: vedi `READY_FOR_PRODUCTION.md`
