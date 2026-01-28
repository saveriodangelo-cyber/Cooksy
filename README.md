# 🍳 Cooksy - Smart Recipe Management Desktop App

## ✨ Features Overview

### Authentication System (New!) 🔐
Cooksy implementa un sistema di autenticazione moderno con **3 metodi sicuri**:

#### 1. **Password PBKDF2**
```
Email → Password (PBKDF2 SHA-256, 160K iterations) → Session
├─ Timing-safe comparison
├─ Per-user random salt
└─ 30-day session tokens
```

#### 2. **2FA OTP Email**
```
Login → 2FA Enabled? → Email 6-digit OTP → Verify → Dashboard
├─ 15-minute validity
├─ Max 5 failed attempts
├─ Brute-force protected
└─ Console logging (SMTP configurable)
```

#### 3. **Passkey WebAuthn** ⭐ NEW
```
Register Biometric → Browser WebAuthn → Challenge-Response → Session
├─ Windows Hello support
├─ Fingerprint / Face ID
├─ Anti-cloning (sign count)
├─ 10-minute challenge TTL
└─ SQLite3 credential storage
```

### Desktop Features
- **Batch Recipe Processing** with timeout/retry logic
- **30+ PDF Templates** with dynamic rendering
- **OCR Extraction** (4 engines: Tesseract, EasyOCR, PaddleOCR, RapidOCR)
- **AI Enrichment** (local Ollama or cloud APIs)
- **Advanced Archive Search** (30+ filters)
- **Subscription Tiers** (Free, Starter, Pro via Stripe)
- **DOCX Export** with nutrition/allergen data
- **Equipment & Allergen Detection** (AI-powered)

---

## 🚀 Quick Start

### Installation
```bash
# Windows
run.cmd

# Starts: Python venv setup → dependencies → Cooksy Desktop App
```

### First Time Usage
1. **Register**: Email + Password (or Passkey)
2. **Optional 2FA**: Confirm 6-digit OTP
3. **Dashboard**: Analyze recipes, export PDFs, manage archive

---

## 🔧 Project Structure

```
ricetta/
├── app/
│   ├── launcher.py           # PyWebView entry point
│   ├── main.py              # Legacy CLI
│   └── web_main.py          # HTTP server
│
├── backend/
│   ├── bridge.py            # API bridge (UI ↔ Backend)
│   ├── user_manager.py      # Authentication + WebAuthn
│   ├── pipeline.py          # OCR, parsing, AI, export
│   ├── archive_db.py        # Recipe database (SQLite)
│   ├── stripe_manager.py    # Payment integration
│   ├── ocr_engines.py       # 4 OCR implementations
│   ├── parser_engine.py     # Recipe text parsing
│   ├── nutrition_db.py      # Nutrition data
│   ├── allergens.py         # Allergen detection
│   └── subscription_manager.py  # Tier management
│
├── ui/
│   ├── index.html           # Main UI
│   ├── app.js               # Frontend logic (2.9K lines)
│   └── stripe_checkout_modal.html
│
├── templates/
│   ├── classico.html        # 30+ PDF templates
│   ├── moderno.html
│   └── assets/              # CSS/fonts
│
├── data/
│   ├── config/              # Configuration files
│   └── recipes/             # SQLite database
│
└── Distribuzione_Cooksy/
    ├── Cooksy.exe           # Standalone executable (400 MB)
    ├── Cooksy_Installer.exe # NSIS installer
    └── Legal docs (termini, privacy, etc)
```

---

## 📦 Build Info

| Component | Details |
|-----------|---------|
| **Format** | Single-file Windows EXE |
| **Size** | 400.75 MB |
| **Runtime** | Python 3.11.9 |
| **Framework** | PyWebView + SQLite3 |
| **Build Tool** | PyInstaller 6.16.0 |
| **Installer** | NSIS 3.11 (with license acceptance) |

---

## 🔐 Authentication Details

### Database Schema
```sql
users
├── id (UUID)
├── email (unique)
├── password_hash (PBKDF2)
├── otp_enabled (0/1)
└── passkey_enrolled (0/1)

user_sessions
├── user_id (FK)
├── token (30-day expiry)
└── created_at

email_otp
├── email
├── otp_code (6-digit)
├── purpose (login/registration)
├── verified_at
├── attempts (max 5)
└── expires_at (15 min)

webauthn_credentials
├── user_id (FK)
├── credential_id (unique)
├── public_key
├── sign_count (anti-clone)
└── last_used_at

webauthn_challenges
├── user_id (FK)
├── challenge_hash (SHA-256)
├── purpose (register/assert)
├── expires_at (10 min TTL)
```

### Security Features
- ✅ PBKDF2 with 160K iterations
- ✅ Timing-safe comparison (`secrets.compare_digest`)
- ✅ Per-user random salt
- ✅ 256-bit entropy tokens
- ✅ OTP brute-force protection (5 attempts)
- ✅ WebAuthn challenge replay protection
- ✅ Sign count tracking (anti-cloning)

---

## 💳 Payments (Stripe Integration)

### Subscription Tiers
| Tier | Price | Limit | Features |
|------|-------|-------|----------|
| **Free** | €0/mo | 5 recipes/mo | Basic export, password auth |
| **Starter** | €4.99/mo | 50 recipes/mo | All templates, 2FA |
| **Pro** | €9.99/mo | Unlimited | AI enrichment, backup, support |

### Implementation
- Stripe Checkout integration
- Webhook handlers for payment events
- Tier-based API quotas
- Automatic grace period handling

---

## 📊 API Reference

### Core Bridge Methods
```python
# Authentication
bridge.auth_register({email, password})
bridge.auth_login({email, password})
bridge.auth_logout({})
bridge.auth_me({})  # Get current user

# Passkey
bridge.passkey_start_registration({})
bridge.passkey_finish_registration({credential_id, client_data, ...})
bridge.passkey_start_assertion({email})
bridge.passkey_finish_assertion({email, credential_id, ...})

# Recipe Processing
bridge.analyze_start({file_path})
bridge.analyze_result({})
bridge.batch_start({folder, category})
bridge.batch_status({})
bridge.export_pdf({recipe_id, template_id})

# Archive
bridge.archive_search({query, filters})
bridge.archive_save_recipe({recipe_data})
bridge.archive_delete({recipe_id})
```

---

## 🧪 Testing

### Run Authentication Tests
```bash
cd backend
python _test_authentication.py

# Output:
# ✓ Password Auth
# ✓ OTP Flow
# ✓ Passkey Challenge
# ✓ Passkey Registration
# ✓ Passkey Authentication
# ✓ Bridge APIs
# TOTALE: 6/6 tests passed
```

---

## 📖 Documentation

- **[AUTHENTICATION_GUIDE.md](AUTHENTICATION_GUIDE.md)** - Complete auth system docs
- **[AUTHENTICATION_IMPLEMENTATION_SUMMARY.md](AUTHENTICATION_IMPLEMENTATION_SUMMARY.md)** - Implementation details
- **[CACHE_DOCUMENTATION.md](CACHE_DOCUMENTATION.md)** - Cache system
- **[OPTIMIZATION_PLAN.md](OPTIMIZATION_PLAN.md)** - Performance improvements
- **[TEMPLATE_RENDERING_IMPL.md](TEMPLATE_RENDERING_IMPL.md)** - Template system

---

## ⚙️ Configuration

### Environment Variables
```bash
# OCR & AI
RICETTEPDF_OLLAMA_URL=http://localhost:11434
RICETTEPDF_OLLAMA_MODEL=mistral
RICETTEPDF_TIMEOUT_S=30
DISABLE_MODEL_SOURCE_CHECK=True

# Stripe (set in data/config/stripe_config.json)
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...

# WebAuthn
WEBAPP_RP_ID=localhost        # Change for production
WEBAPP_RP_NAME=Cooksy
```

### Output Folders
- `Desktop/Elaborate/` - Default export directory
- `Desktop/Elaborate/da_analizzare/` - Deferred files (timeout)
- `Desktop/Elaborate/{category}/` - Category-organized exports

---

## 🛠️ Development

### Python Version
```bash
python --version
# Python 3.11.9
```

### Key Dependencies
```
pywebview>=5.0
SQLite3 (built-in)
Pillow (OCR)
requests (API calls)
stripe (payments)
```

### Build & Distribution
```bash
# Build EXE
python -m PyInstaller Cooksy.spec

# Create Installer
makensis Distribuzione_Cooksy/Cooksy_Installer.iss

# Result
ls Distribuzione_Cooksy/
# Cooksy.exe (400 MB)
# Cooksy_Installer.exe (398 MB)
```

---

## 🚨 Troubleshooting

| Issue | Solution |
|-------|----------|
| Passkey not available | Use password (browser doesn't support WebAuthn) |
| OTP not received | Check SMTP config or console logs |
| PDF export slow | Enable AI caching or use smaller template |
| Batch timeout | Files moved to `da_analizzare` folder |
| DB locked | Close other Cooksy instances |

---

## 📝 License

Commercial Desktop App - See TERMINI_E_CONDIZIONI.txt

---

## 👨‍💻 Support

For issues or feature requests, please contact the development team.

---

**Built with ❤️ using Python + PyWebView**  
**Latest Build: 25/01/2026 11:24:00**  
**Version: 1.0 Production Ready** ✅
