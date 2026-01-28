# GitHub Secrets Setup

Per il deploy automatico, aggiungi questi secrets al repo GitHub:

## Come aggiungerli

1. Vai: https://github.com/TUO_USER/ricetta/settings/secrets/actions
2. Clicca "New repository secret"
3. Aggiungi ciascuno

---

## Secrets Richiesti

### Per Render Deploy

```
RENDER_SERVICE_ID
  Dove trovarla:
  1. Dashboard Render → cooksy-api
  2. Settings → Internal ID
  3. Copy e incolla qui

RENDER_API_KEY
  Dove trovarla:
  1. Account → API Keys
  2. Create API Key
  3. Copy e incolla qui
```

### Per Vercel Deploy

```
VERCEL_TOKEN
  Dove trovarla:
  1. https://vercel.com/account/tokens
  2. Create Token (Scope: Full Account)
  3. Copy e incolla qui

VERCEL_ORG_ID
  Dove trovarla:
  1. https://vercel.com/account/general
  2. Project ID (qui è l'org)
  3. Copy e incolla qui

VERCEL_PROJECT_ID
  Dove trovarla:
  1. Project → Settings → General
  2. Project ID
  3. Copy e incolla qui
```

### Per Stripe Webhooks (opzionale)

```
STRIPE_SECRET_KEY
  sk_live_... (da Stripe Dashboard)

STRIPE_WEBHOOK_SECRET
  whsec_... (da Stripe → Webhooks → Endpoint)
```

---

## Esempio Setup Completo

```yaml
# .github/secrets (visualizza con: gh secret list)
RENDER_SERVICE_ID = srv-c123456789
RENDER_API_KEY = rnd_abc123def456
VERCEL_TOKEN = vercel_abc123def456
VERCEL_ORG_ID = team_abc123def456
VERCEL_PROJECT_ID = prj_abc123def456
STRIPE_SECRET_KEY = sk_live_12345...
```

---

## Test Deploy

Una volta configurati i secrets:

```bash
git push origin main
# Automaticamente:
# 1. render-deploy.yml triggerizza → Deploy backend
# 2. vercel-deploy.yml triggerizza → Deploy frontend

# Verifica logs:
# - GitHub Actions: https://github.com/TUO_USER/ricetta/actions
# - Render: https://dashboard.render.com/cooksy-api/logs
# - Vercel: https://vercel.com/deployments
```

---

## Troubleshooting

**Deployment failed** → Controlla i logs su GitHub Actions

**API not responding** → Check Render logs per error

**Frontend build error** → Check Vercel build logs

**Secrets non trovati** → Assicurati che i nomi matchano esattamente

---

## 🔐 Security Notes

- ✅ Secrets non appaiono in logs
- ✅ Secrets sono encrypted a riposo
- ✅ Only available to Actions
- ✅ Cannot be read once created
- ⚠️ Never commit secrets in code!

---

Una volta fatto, il deploy è **automatico ad ogni git push**! 🚀
