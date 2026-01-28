# Deploy su Railway.app

## Cosa fare ora 👇

1. **Vai su Railway.app**: https://railway.app/dashboard
2. **Clicca "New Project"** → **GitHub Repo**
3. **Seleziona**: `saveriodangelo-cyber/Cooksy`
4. **Railway auto-rileva**:
   - Python 3.11
   - Legge `requirements.txt`
   - Legge `Dockerfile`
5. **Deploy automatico!** ✅

## Se chiede Build Command:
```
pip install -r requirements.txt
```

## Se chiede Start Command:
```
python -m backend.api_rest
```

## Variabili d'ambiente da impostare in Railway:
```
FLASK_ENV=production
FLASK_DEBUG=0
PORT=5000
```

## URL del backend sarà qualcosa come:
```
https://cooksy-prod-xxxxx.railway.app
```

**Vai su Railway ora e connetti il repo!**
