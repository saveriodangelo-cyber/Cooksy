# Test Railway Deployment
Write-Host "🧪 Testing Railway Backend..." -ForegroundColor Cyan

# Test 1: Health check
Write-Host "`n1️⃣ Health Check..." -ForegroundColor Yellow
$health = curl -s https://cooksy-finaly.up.railway.app/api/health | ConvertFrom-Json
if ($health.status -eq "ok") {
    Write-Host "   ✅ Backend is online" -ForegroundColor Green
}
else {
    Write-Host "   ❌ Backend is offline" -ForegroundColor Red
    exit 1
}

# Wait for deployment (if recent push)
Write-Host "`n⏳ Waiting 30 seconds for deployment..." -ForegroundColor Yellow
Start-Sleep -Seconds 30

# Test 2: Auth endpoint (should exist, not return "Unknown method")
Write-Host "`n2️⃣ Testing Auth Login Endpoint..." -ForegroundColor Yellow
$authTest = curl -X POST https://cooksy-finaly.up.railway.app/api/auth_login `
    -H "Content-Type: application/json" `
    -d '{"email":"test","password":"test"}' 2>$null | ConvertFrom-Json

if ($authTest.error -like "*Unknown method*") {
    Write-Host "   ❌ Auth endpoints NOT deployed (still old code)" -ForegroundColor Red
    Write-Host "   Error: $($authTest.error)" -ForegroundColor Red
}
elseif ($authTest.error -like "*Email non valida*" -or $authTest.error -like "*Credenziali*") {
    Write-Host "   ✅ Auth endpoint EXISTS (new code deployed!)" -ForegroundColor Green
    Write-Host "   Error: $($authTest.error) (expected - invalid credentials)" -ForegroundColor Gray
}
else {
    Write-Host "   ⚠️ Unexpected response: $($authTest.error)" -ForegroundColor Yellow
}

# Test 3: Templates endpoint
Write-Host "`n3️⃣ Testing Templates Endpoint..." -ForegroundColor Yellow
$templates = curl -s https://cooksy-finaly.up.railway.app/api/templates | ConvertFrom-Json
if ($templates.ok -eq $true -and $templates.count -gt 0) {
    Write-Host "   ✅ Templates loaded: $($templates.count) templates" -ForegroundColor Green
}
else {
    Write-Host "   ❌ Templates not loaded" -ForegroundColor Red
}

# Test 4: Template HTML endpoint
Write-Host "`n4️⃣ Testing Template HTML Endpoint..." -ForegroundColor Yellow
$templateHtml = curl -s https://cooksy-finaly.up.railway.app/api/templates/classico | ConvertFrom-Json
if ($templateHtml.ok -eq $true -and $templateHtml.html) {
    $htmlLength = $templateHtml.html.Length
    Write-Host "   ✅ Template HTML served ($htmlLength chars)" -ForegroundColor Green
}
else {
    Write-Host "   ❌ Template HTML not available" -ForegroundColor Red
}

Write-Host "`n✅ Testing complete!" -ForegroundColor Green
Write-Host "`n📝 Summary:" -ForegroundColor Cyan
Write-Host "   - Health: $($health.status)" -ForegroundColor White
Write-Host "   - Auth endpoint: $(if ($authTest.error -notlike '*Unknown method*') { 'Deployed ✅' } else { 'Missing ❌' })" -ForegroundColor White
Write-Host "   - Templates: $($templates.count) available" -ForegroundColor White
Write-Host "   - Template HTML: $(if ($templateHtml.ok) { 'Working ✅' } else { 'Not working ❌' })" -ForegroundColor White
