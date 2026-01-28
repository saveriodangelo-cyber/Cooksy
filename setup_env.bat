@echo off
REM Configura le variabili d'ambiente per Ricetta PDF
REM Esegui questo script come Amministratore

setx RICETTEPDF_OPENAI_KEY "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"
setx RICETTEPDF_OPENAI_MODEL "gpt-5.2"

echo.
echo Variabili d'ambiente configurate con successo.
echo Riavviare l'applicazione per applicare i cambiamenti.
pause
