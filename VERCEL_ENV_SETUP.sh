#!/bin/bash
# Script per configurare Vercel environment variables

# Assicurati di essere nel progetto Vercel:
# vercel link (se non già collegato)

# Quindi esegui:
# vercel env add API_BASE_URL

# E inserisci:
# https://cooksy-finaly.up.railway.app

# Oppure via Vercel dashboard:
# 1. Vai a: https://vercel.com/projects/cooksy
# 2. Clicca su "Settings"
# 3. Clicca su "Environment Variables"
# 4. Aggiungi nuova variabile:
#    - Nome: API_BASE_URL
#    - Valore: https://cooksy-finaly.up.railway.app
#    - Ambienti: Production, Preview, Development
# 5. Salva

echo "Per configurare Vercel environment variable:"
echo "1. Vai a: https://vercel.com/projects/cooksy/settings/environment-variables"
echo "2. Clicca 'Add New'"
echo "3. Nome: API_BASE_URL"
echo "4. Valore: https://cooksy-finaly.up.railway.app"
echo "5. Spunta tutti gli ambienti (Production, Preview, Development)"
echo "6. Salva"
echo ""
echo "Oppure usa CLI:"
echo "  vercel env add API_BASE_URL https://cooksy-finaly.up.railway.app"
