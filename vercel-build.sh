#!/bin/bash
# Vercel build script for Cooksy UI

# Copia i file UI nella root se necessario
if [ ! -f "index.html" ] && [ -f "ui/index.html" ]; then
    echo "Copying UI files to root..."
    cp ui/index.html .
    cp ui/*.js .
    cp -r ui/assets . 2>/dev/null || true
fi

echo "Build complete - UI files are ready"
