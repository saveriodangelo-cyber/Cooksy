# -*- coding: utf-8 -*-
"""
Gestione utenti locale con SQLite, password PBKDF2 e scaffolding WebAuthn.
Nota: la verifica crittografica WebAuthn non è implementata (richiede python-fido2).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from backend.app_logging import log_security_event
from backend.utils import project_root

# Base64 URL helpers
def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64url_decode(data: str) -> bytes:
    data = data or ""
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)

try:
    from fido2.client import ClientData
    from fido2.ctap2 import AttestedCredentialData
    from fido2.server import Fido2Server, PublicKeyCredentialDescriptor
    from fido2.webauthn import PublicKeyCredentialRpEntity, PublicKeyCredentialUserEntity
    HAS_FIDO2 = True
except ImportError:
    HAS_FIDO2 = False


def _check_fido2() -> bool:
    """Check dinamico se fido2 è disponibile"""
    try:
        from fido2.server import Fido2Server
        return True
    except ImportError:
        return False


def _import_fido2():
    """Import dinamico dei moduli fido2 quando necessari"""
    try:
        from fido2.client import AttestationObject, AssertionResponse
        from fido2.server import Fido2Server, PublicKeyCredentialDescriptor
        from fido2.webauthn import PublicKeyCredentialRpEntity, PublicKeyCredentialUserEntity
        return {
            'AttestationObject': AttestationObject,
            'AssertionResponse': AssertionResponse,
            'Fido2Server': Fido2Server,
            'PublicKeyCredentialDescriptor': PublicKeyCredentialDescriptor,
            'PublicKeyCredentialRpEntity': PublicKeyCredentialRpEntity,
            'PublicKeyCredentialUserEntity': PublicKeyCredentialUserEntity,
        }
    except ImportError:
        return None


DB_PATH = (project_root() / "data" / "users.db").resolve()
DEFAULT_PBKDF2_ITERS = 120_000
SESSION_ROTATE_SECONDS = 3600  # 1h rotation for long-lived sessions


@dataclass
class User:
    id: str
    email: str
    username: Optional[str]
    role: str
    created_at: str
    last_login: Optional[str]


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat()


def _valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email or ""))


def _password_policy(password: str) -> Tuple[bool, str]:
    if not password or len(password) < 10:
        return False, "La password deve avere almeno 10 caratteri"
    if not re.search(r"[A-Z]", password):
        return False, "Serve almeno una maiuscola"
    if not re.search(r"[a-z]", password):
        return False, "Serve almeno una minuscola"
    if not re.search(r"[0-9]", password):
        return False, "Serve almeno una cifra"
    if not re.search(r"[^A-Za-z0-9]", password):
        return False, "Serve almeno un simbolo"
    return True, ""


def _hash_password(password: str) -> Dict[str, str]:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, DEFAULT_PBKDF2_ITERS)
    return {
        "algo": "pbkdf2_sha256",
        "iterations": str(DEFAULT_PBKDF2_ITERS),
        "salt": base64.b64encode(salt).decode(),
        "hash": base64.b64encode(dk).decode(),
    }


def _verify_password(password: str, stored: Dict[str, Any]) -> bool:
    try:
        if stored.get("algo") != "pbkdf2_sha256":
            return False
        iters = int(stored.get("iterations") or DEFAULT_PBKDF2_ITERS)
        salt = base64.b64decode(stored.get("salt") or "")
        expected = base64.b64decode(stored.get("hash") or "")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
        return secrets.compare_digest(dk, expected)
    except Exception:
        return False


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _random_challenge(length: int = 32) -> str:
    return _b64url(secrets.token_bytes(length))


class UserManager:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()
        self._fido_server = None

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_tables(self) -> None:
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                username TEXT UNIQUE,
                password_algo TEXT NOT NULL,
                password_iterations INTEGER NOT NULL,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                subscription_tier TEXT DEFAULT 'free',
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                subscription_expires_at TEXT,
                twofa_method TEXT DEFAULT 'email',
                twofa_enabled INTEGER DEFAULT 0,
                twofa_verified INTEGER DEFAULT 0,
                passkey_enrolled INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                last_login TEXT
            )
            """
        )
        # Aggiungi colonne se mancano (per DB esistenti)
        cur.execute("PRAGMA table_info(users)")
        existing_cols = {row[1] for row in cur.fetchall()}
        if "twofa_method" not in existing_cols:
            cur.execute("ALTER TABLE users ADD COLUMN twofa_method TEXT DEFAULT 'email'")
        if "twofa_enabled" not in existing_cols:
            cur.execute("ALTER TABLE users ADD COLUMN twofa_enabled INTEGER DEFAULT 0")
        if "twofa_verified" not in existing_cols:
            cur.execute("ALTER TABLE users ADD COLUMN twofa_verified INTEGER DEFAULT 0")
        if "passkey_enrolled" not in existing_cols:
            cur.execute("ALTER TABLE users ADD COLUMN passkey_enrolled INTEGER DEFAULT 0")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                device TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS login_attempts (
                email TEXT PRIMARY KEY,
                failures INTEGER DEFAULT 0,
                locked_until TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS login_rate_limit (
                email TEXT PRIMARY KEY,
                bucket_start TEXT NOT NULL,
                attempts INTEGER NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS webauthn_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                credential_id TEXT NOT NULL UNIQUE,
                public_key TEXT NOT NULL,
                sign_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS email_otp (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                otp_code TEXT NOT NULL,
                purpose TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                verified_at TEXT,
                attempts INTEGER DEFAULT 0,
                locked_until TEXT,
                UNIQUE(email, purpose)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS webauthn_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                challenge_hash TEXT NOT NULL,
                purpose TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                challenge TEXT,
                state TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute("PRAGMA table_info(webauthn_challenges)")
        wa_cols = {row[1] for row in cur.fetchall()}
        if "challenge" not in wa_cols:
            cur.execute("ALTER TABLE webauthn_challenges ADD COLUMN challenge TEXT")
        if "state" not in wa_cols:
            cur.execute("ALTER TABLE webauthn_challenges ADD COLUMN state TEXT")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                year_month TEXT NOT NULL,
                recipes_analyzed INTEGER DEFAULT 0,
                storage_used_mb REAL DEFAULT 0,
                api_calls INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, year_month),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                year_month TEXT NOT NULL,
                recipes_analyzed INTEGER DEFAULT 0,
                storage_used_mb REAL DEFAULT 0,
                api_calls INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, year_month),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.commit()
        conn.close()

    # ---------- CRUD Utenti ----------
    def register(self, email: str, password: str, username: Optional[str] = None, role: str = "user") -> Dict[str, Any]:
        email = (email or "").strip().lower()
        if not email or not password:
            return {"ok": False, "error": "Email e password sono obbligatorie"}
        if not _valid_email(email):
            return {"ok": False, "error": "Email non valida"}
        ok_pwd, err_pwd = _password_policy(password)
        if not ok_pwd:
            return {"ok": False, "error": err_pwd}

        conn = self._conn()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cur.fetchone():
            conn.close()
            return {"ok": False, "error": "Email già registrata"}

        ph = _hash_password(password)
        user_id = secrets.token_hex(12)
        now = _utcnow_iso()
        try:
            cur.execute(
                """
                INSERT INTO users (id, email, username, password_algo, password_iterations, password_salt, password_hash, role, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    email,
                    username,
                    ph["algo"],
                    int(ph["iterations"]),
                    ph["salt"],
                    ph["hash"],
                    role,
                    now,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError as e:
            conn.close()
            if "users.username" in str(e):
                return {"ok": False, "error": "Username già in uso"}
            elif "users.email" in str(e):
                return {"ok": False, "error": "Email già registrata"}
            else:
                return {"ok": False, "error": "Errore durante la registrazione"}
        conn.close()
        return {"ok": True, "user_id": user_id}

    def _row_to_user(self, row: sqlite3.Row) -> User:
        return User(
            id=row[0],
            email=row[1],
            username=row[2],
            role=row[7],
            created_at=row[8],
            last_login=row[9],
        )

    def authenticate(self, email: str, password: str) -> Dict[str, Any]:
        email = (email or "").strip().lower()
        if not _valid_email(email):
            log_security_event(event="auth", status="fail", user_id=email, detail="Email non valida")
            return {"ok": False, "error": "Email non valida"}
        conn = self._conn()
        cur = conn.cursor()
        limited, wait_s = self._rate_limit_check(cur, email)
        if limited:
            conn.close()
            log_security_event(event="auth", status="blocked", user_id=email, detail=f"Troppi tentativi, wait {wait_s}s")
            return {"ok": False, "error": f"Troppi tentativi, riprova tra {wait_s} secondi"}
        locked, wait_s = self._is_locked(cur, email)
        if locked:
            conn.close()
            log_security_event(event="auth", status="locked", user_id=email, detail=f"Account lock {wait_s}s")
            return {"ok": False, "error": f"Account temporaneamente bloccato. Riprova tra {wait_s} secondi"}

        cur.execute(
            "SELECT id, email, username, password_algo, password_iterations, password_salt, password_hash, role, created_at, last_login FROM users WHERE email = ?",
            (email,),
        )
        row = cur.fetchone()
        if not row:
            self._register_failure(cur, email)
            self._rate_limit_hit(cur, email)
            conn.commit()
            conn.close()
            log_security_event(event="auth", status="fail", user_id=email, detail="Utente non trovato")
            return {"ok": False, "error": "Credenziali non valide"}

        stored = {
            "algo": row[3],
            "iterations": str(row[4]),
            "salt": row[5],
            "hash": row[6],
        }
        if not _verify_password(password, stored):
            self._register_failure(cur, email)
            self._rate_limit_hit(cur, email)
            conn.commit()
            conn.close()
            log_security_event(event="auth", status="fail", user_id=email, detail="Password errata")
            return {"ok": False, "error": "Credenziali non valide"}

        user_id = row[0]
        cur.execute("UPDATE users SET last_login = ? WHERE id = ?", (_utcnow_iso(), user_id))
        self._reset_failures(cur, email)
        self._rate_limit_reset(cur, email)
        cur.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()

        token_info = self._create_session(cur, user_id)
        conn.commit()
        conn.close()
        log_security_event(event="auth", status="ok", user_id=user_id, detail="Login riuscito")
        return {"ok": True, "user_id": user_id, **token_info}

    def _create_session(self, cur: sqlite3.Cursor, user_id: str, days: int = 30) -> Dict[str, Any]:
        token = secrets.token_urlsafe(32)
        now = datetime.utcnow()
        expires = now + timedelta(days=days)
        cur.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, now.isoformat(), expires.isoformat()),
        )
        return {"token": token, "expires_at": expires.isoformat()}

    def create_session(self, user_id: str, days: int = 30) -> str:
        """Crea una nuova sessione per user_id. Ritorna il token."""
        conn = self._conn()
        cur = conn.cursor()
        result = self._create_session(cur, user_id, days=days)
        conn.commit()
        conn.close()
        return result.get("token", "")

    def _rotate_session(self, cur: sqlite3.Cursor, *, old_token: str, user_id: str, expires_at: datetime) -> Dict[str, Any]:
        cur.execute("DELETE FROM sessions WHERE token = ?", (old_token,))
        new_token = secrets.token_urlsafe(32)
        now = datetime.utcnow().isoformat()
        cur.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (new_token, user_id, now, expires_at.isoformat()),
        )
        return {"token": new_token, "expires_at": expires_at.isoformat(), "rotated": True}

    def _is_locked(self, cur: sqlite3.Cursor, email: str) -> Tuple[bool, int]:
        cur.execute("SELECT failures, locked_until FROM login_attempts WHERE email = ?", (email,))
        row = cur.fetchone()
        if not row:
            return False, 0
        locked_until = row[1]
        if not locked_until:
            return False, 0
        try:
            dt = datetime.fromisoformat(locked_until)
            now = datetime.utcnow()
            if dt > now:
                return True, int((dt - now).total_seconds())
        except Exception:
            return False, 0
        return False, 0

    def _register_failure(self, cur: sqlite3.Cursor, email: str) -> None:
        cur.execute("SELECT failures FROM login_attempts WHERE email = ?", (email,))
        row = cur.fetchone()
        failures = int(row[0]) if row else 0
        failures += 1
        lock_until = None
        if failures >= 5:
            lock_until = (datetime.utcnow() + timedelta(minutes=5)).isoformat()
        cur.execute(
            "INSERT OR REPLACE INTO login_attempts (email, failures, locked_until) VALUES (?, ?, ?)",
            (email, failures, lock_until),
        )

    def _reset_failures(self, cur: sqlite3.Cursor, email: str) -> None:
        cur.execute(
            "INSERT OR REPLACE INTO login_attempts (email, failures, locked_until) VALUES (?, 0, NULL)",
            (email,),
        )

    def _rate_limit_check(self, cur: sqlite3.Cursor, email: str, max_attempts: int = 10, window_seconds: int = 60) -> Tuple[bool, int]:
        if not email:
            return False, 0
        now = datetime.utcnow()
        bucket_start = now.replace(second=0, microsecond=0)
        cur.execute(
            "SELECT bucket_start, attempts FROM login_rate_limit WHERE email = ?",
            (email,),
        )
        row = cur.fetchone()
        if not row:
            return False, 0
        try:
            bucket_dt = datetime.fromisoformat(row[0])
        except Exception:
            return False, 0
        if bucket_dt != bucket_start:
            return False, 0
        attempts = int(row[1]) if row[1] is not None else 0
        if attempts >= max_attempts:
            elapsed = (now - bucket_dt).total_seconds()
            wait = max(1, window_seconds - int(elapsed))
            return True, wait
        return False, 0

    def _rate_limit_hit(self, cur: sqlite3.Cursor, email: str) -> None:
        if not email:
            return
        bucket_start = datetime.utcnow().replace(second=0, microsecond=0)
        cur.execute(
            "SELECT bucket_start, attempts FROM login_rate_limit WHERE email = ?",
            (email,),
        )
        row = cur.fetchone()
        if not row or row[0] != bucket_start.isoformat():
            cur.execute(
                "INSERT OR REPLACE INTO login_rate_limit (email, bucket_start, attempts) VALUES (?, ?, ?)",
                (email, bucket_start.isoformat(), 1),
            )
        else:
            cur.execute(
                "UPDATE login_rate_limit SET attempts = attempts + 1 WHERE email = ?",
                (email,),
            )

    def _rate_limit_reset(self, cur: sqlite3.Cursor, email: str) -> None:
        if not email:
            return
        cur.execute("DELETE FROM login_rate_limit WHERE email = ?", (email,))

    def validate_session(self, token: str) -> Dict[str, Any]:
        """Valida sessione e ruota token se più vecchio di SESSION_ROTATE_SECONDS."""
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, created_at, expires_at FROM sessions WHERE token = ?",
            (token,),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            log_security_event(event="session", status="fail", user_id=None, detail="Token non trovato")
            return {"ok": False, "error": "Sessione non valida"}

        user_id, created_at, expires_at = row[0], row[1], row[2]
        now = datetime.utcnow()
        try:
            exp_dt = datetime.fromisoformat(expires_at)
            if exp_dt < now:
                cur.execute("DELETE FROM sessions WHERE token = ?", (token,))
                conn.commit()
                conn.close()
                log_security_event(event="session", status="expired", user_id=user_id, detail="Token scaduto")
                return {"ok": False, "error": "Sessione scaduta"}
            created_dt = datetime.fromisoformat(created_at)
        except Exception:
            conn.close()
            return {"ok": False, "error": "Sessione non valida"}

        age_s = (now - created_dt).total_seconds()
        if age_s > SESSION_ROTATE_SECONDS:
            rotated = self._rotate_session(cur, old_token=token, user_id=user_id, expires_at=exp_dt)
            conn.commit()
            conn.close()
            log_security_event(event="session", status="rotated", user_id=user_id, detail="Token ruotato")
            return {"ok": True, "user_id": user_id, **rotated}

        conn.close()
        return {"ok": True, "user_id": user_id, "rotated": False}

    def logout(self, token: str) -> Dict[str, Any]:
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        log_security_event(event="logout", status="ok", user_id=None, detail="Sessione terminata")
        return {"ok": True}

    # ---------- WebAuthn / Passkey (senza verifica firma) ----------
    def _cleanup_challenges(self, cur: sqlite3.Cursor) -> None:
        now = datetime.utcnow().isoformat()
        cur.execute("DELETE FROM webauthn_challenges WHERE expires_at < ?", (now,))

    def _store_challenge(self, cur: sqlite3.Cursor, user_id: str, purpose: str, ttl_seconds: int = 300, *, state: Optional[str] = None, challenge: Optional[str] = None) -> str:
        self._cleanup_challenges(cur)
        challenge_val = challenge or _random_challenge()
        ch_hash = _sha256_hex(challenge_val)
        now = datetime.utcnow()
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
        cur.execute(
            "DELETE FROM webauthn_challenges WHERE user_id = ? AND purpose = ?",
            (user_id, purpose),
        )
        cur.execute(
            """
            INSERT INTO webauthn_challenges (user_id, challenge_hash, purpose, created_at, expires_at, challenge, state)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, ch_hash, purpose, now.isoformat(), expires_at, challenge_val, state),
        )
        return challenge_val

    def _consume_challenge(self, cur: sqlite3.Cursor, user_id: str, purpose: str, challenge: str) -> Tuple[bool, str, Optional[str]]:
        self._cleanup_challenges(cur)
        cur.execute(
            "SELECT id, challenge_hash, state, challenge FROM webauthn_challenges WHERE user_id = ? AND purpose = ?",
            (user_id, purpose),
        )
        row = cur.fetchone()
        if not row:
            return False, "Challenge non trovata", None
        stored_hash = row[1]
        cur.execute("DELETE FROM webauthn_challenges WHERE id = ?", (row[0],))
        if not secrets.compare_digest(stored_hash, _sha256_hex(challenge)):
            return False, "Challenge non valida", None
        return True, "", row[2]

    def _rp_id(self) -> str:
        return os.environ.get("WEBAPP_RP_ID", "localhost")

    def _rp_name(self) -> str:
        return os.environ.get("WEBAPP_RP_NAME", "Cooksy")

    def _rp_origin(self) -> str:
        return os.environ.get("WEBAPP_ORIGIN", "http://localhost:35432")

    def _fido2_server(self) -> Any:
        if self._fido_server is not None:
            return self._fido_server
        fido2_mods = _import_fido2()
        if not fido2_mods:
            raise RuntimeError("python-fido2 non disponibile")
        PublicKeyCredentialRpEntity = fido2_mods['PublicKeyCredentialRpEntity']
        Fido2Server = fido2_mods['Fido2Server']
        rp = PublicKeyCredentialRpEntity(id=self._rp_id(), name=self._rp_name())
        self._fido_server = Fido2Server(rp)
        return self._fido_server

    class _StoredCredential:
        """Wrapper per credenziali FIDO2 storate in DB. Compatibile con fido2.server."""
        def __init__(self, cred_id: bytes, public_key: bytes, sign_count: int):
            self.credential_id = cred_id
            self.public_key = public_key
            self.sign_count = sign_count
        
        # Proprietà richieste da fido2.server.authenticate_complete
        @property
        def public_key_bytes(self) -> bytes:
            """Alias per public_key per compatibilità fido2"""
            return self.public_key
        
        def to_dict(self) -> Dict[str, Any]:
            return {
                "credential_id": self.credential_id,
                "public_key": self.public_key,
                "sign_count": self.sign_count,
            }

    def webauthn_start_registration(self, user_id: str, email: str, username: Optional[str] = None) -> Dict[str, Any]:
        if not _check_fido2():
            return {"ok": False, "error": "python-fido2 mancante"}
        if not user_id:
            return {"ok": False, "error": "User mancante"}
        try:
            fido2_mods = _import_fido2()
            if not fido2_mods:
                return {"ok": False, "error": "python-fido2 non importabile"}
            PublicKeyCredentialUserEntity = fido2_mods['PublicKeyCredentialUserEntity']
            
            server = self._fido2_server()
            user = PublicKeyCredentialUserEntity(id=user_id.encode("utf-8"), name=email, display_name=username or email)
            registration_data, state = server.register_begin(
                user,
                credentials=[],
                resident_key_requirement="preferred",
                user_verification="preferred",
                authenticator_attachment=None,
            )
            challenge_b64 = _b64url(registration_data.public_key.challenge)
            state_json = json.dumps(state)
            conn = self._conn()
            cur = conn.cursor()
            self._store_challenge(cur, user_id, "register", state=state_json, challenge=challenge_b64)
            conn.commit()
            conn.close()
            # Convert to dict per risposta frontend
            return {
                "ok": True,
                "challenge": challenge_b64,
                "rpId": registration_data.public_key.rp.get("id", self._rp_id()),
                "rpName": registration_data.public_key.rp.get("name", self._rp_name()),
                "user": {
                    "id": _b64url(registration_data.public_key.user.id),
                    "name": registration_data.public_key.user.name,
                    "displayName": registration_data.public_key.user.display_name,
                },
                "pubKeyCredParams": [{"type": "public-key", "alg": alg} for alg in registration_data.public_key.pub_key_cred_params],
                "timeout": registration_data.public_key.timeout or 60000,
                "attestation": registration_data.public_key.attestation or "none",
                "authenticatorSelection": {
                    "residentKey": "preferred",
                    "userVerification": "preferred",
                },
            }
        except Exception as e:
            return {"ok": False, "error": f"reg begin: {e}"}

    def webauthn_finish_registration(
        self,
        user_id: str,
        credential_id: str,
        attestation_object: str,
        client_data_json: str,
        challenge: str,
    ) -> Dict[str, Any]:
        if not _check_fido2():
            return {"ok": False, "error": "python-fido2 mancante"}
        if not (credential_id and attestation_object and client_data_json and challenge):
            return {"ok": False, "error": "Dati passkey mancanti"}
        
        try:
            conn = self._conn()
            cur = conn.cursor()
            
            # Consume challenge (replay protection)
            ok_ch, err_ch, state_json = self._consume_challenge(cur, user_id, "register", challenge)
            if not ok_ch:
                conn.close()
                log_security_event("webauthn_register", "failed", user_id=user_id, detail=f"Challenge error: {err_ch}")
                return {"ok": False, "error": "Challenge non valido o scaduto"}
            
            if not state_json:
                conn.close()
                log_security_event("webauthn_register", "failed", user_id=user_id, detail="State mancante")
                return {"ok": False, "error": "Stato registrazione mancante"}
            
            state = json.loads(state_json)
            server = self._fido2_server()
            
            # Verify attestation (crittographic verification)
            auth_data = server.register_complete(
                state,
                _b64url_decode(client_data_json),
                _b64url_decode(attestation_object),
            )
            
            # Extract credential data
            cred = auth_data.credential_data
            if not cred:
                conn.close()
                log_security_event("webauthn_register", "failed", user_id=user_id, detail="Credential data mancante")
                return {"ok": False, "error": "Dati credenziale mancanti nella risposta"}
            
            cred_id_b64 = _b64url(cred.credential_id)
            pubkey_b64 = _b64url(cred.public_key) if hasattr(cred, "public_key") else _b64url(cred.public_key_bytes)
            
            # Check for duplicate credential
            cur.execute("SELECT id FROM webauthn_credentials WHERE credential_id = ?", (cred_id_b64,))
            if cur.fetchone():
                conn.close()
                log_security_event("webauthn_register", "failed", user_id=user_id, detail="Credential ID duplicato")
                return {"ok": False, "error": "Credenziale già registrata (ID duplicato)"}
            
            # Store credential
            cur.execute(
                """
                INSERT INTO webauthn_credentials (user_id, credential_id, public_key, sign_count, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, cred_id_b64, pubkey_b64, int(auth_data.sign_count or 0), datetime.utcnow().isoformat()),
            )
            cur.execute("UPDATE users SET passkey_enrolled = 1 WHERE id = ?", (user_id,))
            conn.commit()
            conn.close()
            
            log_security_event("webauthn_register", "ok", user_id=user_id, detail="Passkey registrata e verificata")
            return {"ok": True}
            
        except Exception as e:
            log_security_event("webauthn_register", "error", user_id=user_id, detail=str(e))
            return {"ok": False, "error": f"Registrazione passkey fallita: Attestazione non valida o corrotta"}

    def webauthn_start_assertion(self, user_id: str) -> Dict[str, Any]:
        if not _check_fido2():
            return {"ok": False, "error": "python-fido2 mancante"}
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT credential_id, public_key, sign_count FROM webauthn_credentials WHERE user_id = ?",
            (user_id,),
        )
        rows = cur.fetchall()
        if not rows:
            conn.close()
            return {"ok": False, "error": "Nessuna passkey registrata"}
        credentials = []
        for r in rows:
            cid = _b64url_decode(r[0])
            pub = _b64url_decode(r[1])
            sc = int(r[2] or 0)
            credentials.append(self._StoredCredential(cid, pub, sc))
        server = self._fido2_server()
        auth_data, state = server.authenticate_begin(credentials, user_verification="preferred")
        challenge_b64 = _b64url(auth_data["challenge"])
        state_json = json.dumps(state)
        self._store_challenge(cur, user_id, "assert", state=state_json, challenge=challenge_b64)
        conn.commit()
        conn.close()
        allow = auth_data.get("allowCredentials", [])
        # Convert allowCredentials ids to b64url strings
        allow_clean = []
        for a in allow:
            cid = a.get("id")
            cid_b64 = _b64url(cid) if isinstance(cid, (bytes, bytearray)) else cid
            allow_clean.append({"type": a.get("type", "public-key"), "id": cid_b64})
        return {
            "ok": True,
            "challenge": challenge_b64,
            "rpId": auth_data.get("rpId", self._rp_id()),
            "allowCredentials": allow_clean,
            "timeout": auth_data.get("timeout", 60000),
        }

    def webauthn_finish_assertion(
        self,
        user_id: str,
        credential_id: str,
        authenticator_data: str,
        client_data_json: str,
        signature: str,
        challenge: str,
    ) -> Dict[str, Any]:
        if not _check_fido2():
            return {"ok": False, "error": "python-fido2 mancante"}
        if not (credential_id and authenticator_data and client_data_json and signature and challenge):
            return {"ok": False, "error": "Dati passkey mancanti"}
        
        email = None
        try:
            conn = self._conn()
            cur = conn.cursor()
            
            # Get email per logging
            cur.execute("SELECT email FROM users WHERE id = ?", (user_id,))
            row = cur.fetchone()
            if row:
                email = row[0]
            
            # Consume challenge (replay protection)
            ok_ch, err_ch, state_json = self._consume_challenge(cur, user_id, "assert", challenge)
            if not ok_ch:
                conn.close()
                log_security_event("webauthn_assert", "failed", user_id=user_id, detail=f"Challenge error: {err_ch}")
                return {"ok": False, "error": "Challenge non valido o scaduto"}
            
            if not state_json:
                conn.close()
                log_security_event("webauthn_assert", "failed", user_id=user_id, detail="State mancante")
                return {"ok": False, "error": "Stato autenticazione mancante"}
            
            # Fetch stored credential
            state = json.loads(state_json)
            cur.execute(
                "SELECT credential_id, public_key, sign_count FROM webauthn_credentials WHERE user_id = ? AND credential_id = ?",
                (user_id, credential_id),
            )
            row = cur.fetchone()
            if not row:
                conn.close()
                log_security_event("webauthn_assert", "failed", user_id=user_id, detail="Passkey non trovata")
                return {"ok": False, "error": "Passkey non registrata"}
            
            stored_pub = _b64url_decode(row[1])
            stored_sign = int(row[2] or 0)
            cred_id_bytes = _b64url_decode(credential_id)
            cred_obj = self._StoredCredential(cred_id_bytes, stored_pub, stored_sign)
            
            # Prepare data for verification
            server = self._fido2_server()
            authr_data = _b64url_decode(authenticator_data)
            client_data = _b64url_decode(client_data_json)
            sig = _b64url_decode(signature)
            
            # Verify signature and sign_count (crittographic verification by fido2)
            res = server.authenticate_complete(
                state,
                [cred_obj],
                cred_id_bytes,
                client_data,
                authr_data,
                sig,
            )
            
            # Check for credential cloning (sign count must increase)
            new_sign_count = res.new_sign_count if hasattr(res, "new_sign_count") else stored_sign + 1
            if new_sign_count <= stored_sign and stored_sign > 0:
                conn.close()
                log_security_event("webauthn_assert", "failed", user_id=user_id, detail=f"Sign count check failed: stored={stored_sign}, new={new_sign_count}")
                return {"ok": False, "error": "Autenticatore clonato rilevato (sign count regressione)"}
            
            # Update credential
            cur.execute(
                "UPDATE webauthn_credentials SET sign_count = ?, last_used_at = ? WHERE credential_id = ?",
                (int(new_sign_count), datetime.utcnow().isoformat(), credential_id),
            )
            
            # Create session
            token_info = self._create_session(cur, user_id)
            cur.execute("UPDATE users SET last_login = ? WHERE id = ?", (_utcnow_iso(), user_id))
            conn.commit()
            conn.close()
            
            log_security_event("webauthn_assert", "ok", user_id=user_id, detail="Autenticazione passkey riuscita")
            return {"ok": True, **token_info}
            
        except Exception as e:
            log_security_event("webauthn_assert", "error", user_id=user_id, detail=str(e))
            return {"ok": False, "error": f"Autenticazione passkey fallita: Firma non valida o dati corrotti"}

    # ---------- Subscription Tier Management ----------
    def set_subscription_tier(self, user_id: str, tier: str, stripe_customer_id: Optional[str] = None, stripe_subscription_id: Optional[str] = None, expires_at: Optional[str] = None) -> Dict[str, Any]:
        """Imposta il tier di sottoscrizione di un utente"""
        conn = self._conn()
        cur = conn.cursor()
        
        cur.execute(
            "UPDATE users SET subscription_tier = ?, stripe_customer_id = ?, stripe_subscription_id = ?, subscription_expires_at = ? WHERE id = ?",
            (tier, stripe_customer_id, stripe_subscription_id, expires_at, user_id)
        )
        
        conn.commit()
        conn.close()
        return {"ok": True, "tier": tier}

    def get_subscription_tier(self, user_id: str) -> Optional[str]:
        """Recupera il tier di sottoscrizione di un utente"""
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("SELECT subscription_tier FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else "free"

    def get_user_subscription_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Recupera info completa di sottoscrizione"""
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT subscription_tier, stripe_customer_id, stripe_subscription_id, subscription_expires_at FROM users WHERE id = ?",
            (user_id,)
        )
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return {
            "tier": row[0] or "free",
            "stripe_customer_id": row[1],
            "stripe_subscription_id": row[2],
            "expires_at": row[3],
        }

    def track_recipe_analyzed(self, user_id: str) -> Dict[str, Any]:
        """Incrementa il contatore di ricette analizzate per questo mese"""
        year_month = datetime.utcnow().strftime("%Y-%m")
        conn = self._conn()
        cur = conn.cursor()
        
        # Verifica se esiste già un record per questo mese
        cur.execute(
            "SELECT id, recipes_analyzed FROM usage_tracking WHERE user_id = ? AND year_month = ?",
            (user_id, year_month)
        )
        row = cur.fetchone()
        
        if row:
            # Incrementa il contatore
            cur.execute(
                "UPDATE usage_tracking SET recipes_analyzed = recipes_analyzed + 1 WHERE id = ?",
                (row[0],)
            )
        else:
            # Crea un nuovo record
            cur.execute(
                "INSERT INTO usage_tracking (user_id, year_month, recipes_analyzed, created_at) VALUES (?, ?, 1, ?)",
                (user_id, year_month, datetime.utcnow().isoformat())
            )
        
        conn.commit()
        conn.close()
        return {"ok": True, "month": year_month}

    def get_monthly_usage(self, user_id: str, year_month: Optional[str] = None) -> Dict[str, Any]:
        """Recupera l'utilizzo mensile di un utente"""
        if not year_month:
            year_month = datetime.utcnow().strftime("%Y-%m")
        
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT recipes_analyzed, storage_used_mb, api_calls FROM usage_tracking WHERE user_id = ? AND year_month = ?",
            (user_id, year_month)
        )
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return {
                "month": year_month,
                "recipes_analyzed": 0,
                "storage_used_mb": 0.0,
                "api_calls": 0,
            }
        
        return {
            "month": year_month,
            "recipes_analyzed": row[0],
            "storage_used_mb": row[1],
            "api_calls": row[2],
        }

    def get_user(self, user_id: str) -> Optional[User]:
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, username, password_algo, password_iterations, password_salt, password_hash, role, created_at, last_login FROM users WHERE id = ?",
            (user_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_user(row)

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        return self.get_user(user_id)

    # ---------- 2FA Email OTP ----------
    def generate_email_otp(self, email: str, purpose: str = "registration", validity_minutes: int = 15) -> str:
        """Genera e salva un OTP 6-digit per email. Ritorna il codice."""
        otp_code = str(secrets.randbelow(1000000)).zfill(6)
        now = datetime.utcnow()
        expires_at = (now + timedelta(minutes=validity_minutes)).isoformat()
        
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO email_otp (email, otp_code, purpose, created_at, expires_at, attempts) VALUES (?, ?, ?, ?, ?, 0)",
            (email.lower(), otp_code, purpose, now.isoformat(), expires_at)
        )
        conn.commit()
        conn.close()
        return otp_code

    def verify_email_otp(self, email: str, otp_code: str, purpose: str = "registration", max_attempts: int = 5) -> Dict[str, Any]:
        """Verifica l'OTP per email. Ritorna ok=True se valido."""
        email = (email or "").strip().lower()
        otp_code = (otp_code or "").strip()
        
        if not email or not otp_code or len(otp_code) != 6:
            return {"ok": False, "error": "Codice OTP non valido"}
        
        conn = self._conn()
        cur = conn.cursor()
        now = datetime.utcnow()
        
        cur.execute(
            "SELECT id, otp_code, expires_at, attempts, locked_until FROM email_otp WHERE email = ? AND purpose = ? AND verified_at IS NULL ORDER BY created_at DESC LIMIT 1",
            (email, purpose)
        )
        row = cur.fetchone()
        
        if not row:
            conn.close()
            return {"ok": False, "error": "Nessun OTP trovato per questa email"}
        
        otp_id, stored_otp, expires_at_str, attempts, locked_until = row
        
        # Controlla lock
        if locked_until:
            try:
                lock_dt = datetime.fromisoformat(locked_until)
                if lock_dt > now:
                    wait_s = int((lock_dt - now).total_seconds())
                    conn.close()
                    return {"ok": False, "error": f"Troppi tentativi errati. Riprova tra {wait_s} secondi"}
            except Exception:
                pass
        
        # Controlla scadenza
        try:
            exp_dt = datetime.fromisoformat(expires_at_str)
            if exp_dt < now:
                conn.close()
                return {"ok": False, "error": "OTP scaduto"}
        except Exception:
            conn.close()
            return {"ok": False, "error": "Errore interno (expires_at invalido)"}
        
        # Controlla tentativi
        if attempts >= max_attempts:
            # Lock per 5 minuti
            lock_until = (now + timedelta(minutes=5)).isoformat()
            cur.execute("UPDATE email_otp SET locked_until = ? WHERE id = ?", (lock_until, otp_id))
            conn.commit()
            conn.close()
            return {"ok": False, "error": f"Troppi tentativi errati. Richiedi un nuovo OTP tra 5 minuti"}
        
        # Confronta OTP con timing costante
        if not secrets.compare_digest(otp_code, stored_otp):
            cur.execute("UPDATE email_otp SET attempts = attempts + 1 WHERE id = ?", (otp_id,))
            conn.commit()
            conn.close()
            return {"ok": False, "error": "Codice OTP errato"}
        
        # OTP corretto
        verified_at = now.isoformat()
        cur.execute("UPDATE email_otp SET verified_at = ?, attempts = 0, locked_until = NULL WHERE id = ?", (verified_at, otp_id))
        conn.commit()
        conn.close()
        return {"ok": True}

    def send_otp_email(self, email: str, otp_code: str) -> Dict[str, Any]:
        """Invia OTP via email. Placeholder per integrazione SMTP."""
        # TODO: Integrare con smtplib per inviare email reale
        # Per ora logga il codice in console per testing
        print(f"[2FA] OTP per {email}: {otp_code}")
        return {"ok": True, "message": "OTP inviato (console logging per ora)"}

    def send_otp_sms(self, email: str, otp_code: str) -> Dict[str, Any]:
        """Invia OTP via SMS. Placeholder per integrazione Twilio."""
        # TODO: Integrare con Twilio per inviare SMS reale
        # Per ora logga il codice in console per testing
        print(f"[2FA-SMS] OTP per {email}: {otp_code}")
        return {"ok": True, "message": "OTP inviato via SMS (console logging per ora)"}

    def send_otp(self, email: str, otp_code: str, method: str = "email") -> Dict[str, Any]:
        """Invia OTP via email o SMS a seconda del metodo scelto."""
        if method == "sms":
            return self.send_otp_sms(email, otp_code)
        else:
            return self.send_otp_email(email, otp_code)

    # ---------- WebAuthn Passkey ----------
    def _get_fido2_server(self) -> Optional[Fido2Server]:
        """Crea un'istanza Fido2Server se python-fido2 è disponibile."""
        if not _check_fido2():
            return None
        try:
            rp = PublicKeyCredentialRpEntity("localhost", "RicettePDF")
            return Fido2Server(rp)
        except Exception:
            return None

    def start_passkey_registration(self, user_id: str, email: str) -> Dict[str, Any]:
        """Inizia il flusso di registrazione passkey. Ritorna challengeOptions."""
        if not _check_fido2():
            return {"ok": False, "error": "WebAuthn non disponibile"}
        
        user = self.get_user(user_id)
        if not user:
            return {"ok": False, "error": "Utente non trovato"}
        
        server = self._get_fido2_server()
        if not server:
            return {"ok": False, "error": "Server FIDO2 non configurato"}
        
        try:
            user_entity = PublicKeyCredentialUserEntity(user_id, email, email)
            registration_data, state = server.register_begin(user_entity, [])
            
            # Salva lo state challenge nel DB
            challenge_hash = state.challenge
            conn = self._conn()
            cur = conn.cursor()
            now = datetime.utcnow()
            expires_at = (now + timedelta(minutes=10)).isoformat()
            cur.execute(
                "INSERT INTO webauthn_challenges (user_id, challenge_hash, purpose, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, challenge_hash, "registration", now.isoformat(), expires_at)
            )
            conn.commit()
            conn.close()
            
            # Ritorna le opzioni di registrazione (serializzate come JSON)
            import json
            options_json = json.dumps(registration_data, default=lambda o: o.__dict__ if hasattr(o, '__dict__') else str(o))
            return {"ok": True, "options": options_json}
        except Exception as e:
            return {"ok": False, "error": f"Errore registrazione passkey: {str(e)}"}

    def complete_passkey_registration(self, user_id: str, response_json: str) -> Dict[str, Any]:
        """Completa la registrazione passkey. response_json è il ClientAssertionResponse."""
        if not _check_fido2():
            return {"ok": False, "error": "WebAuthn non disponibile"}
        
        try:
            server = self._get_fido2_server()
            if not server:
                return {"ok": False, "error": "Server FIDO2 non configurato"}
            
            response_data = json.loads(response_json)
            
            conn = self._conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT challenge_hash FROM webauthn_challenges WHERE user_id = ? AND purpose = ? AND expires_at > ? ORDER BY created_at DESC LIMIT 1",
                (user_id, "registration", datetime.utcnow().isoformat())
            )
            row = cur.fetchone()
            if not row:
                conn.close()
                return {"ok": False, "error": "Challenge non trovato o scaduto"}
            
            # Completa la registrazione
            credential_data = server.register_complete(
                bytes.fromhex(row[0]),  # challenge_hash
                response_data
            )
            
            # Salva il credential nel DB
            cred_id = base64.b64encode(credential_data.credential_id).decode()
            pub_key = base64.b64encode(credential_data.credential_public_key).decode()
            now = datetime.utcnow().isoformat()
            
            cur.execute(
                "INSERT INTO webauthn_credentials (user_id, credential_id, public_key, created_at) VALUES (?, ?, ?, ?)",
                (user_id, cred_id, pub_key, now)
            )
            cur.execute("UPDATE users SET passkey_enrolled = 1 WHERE id = ?", (user_id,))
            conn.commit()
            conn.close()
            
            return {"ok": True, "message": "Passkey registrato con successo"}
        except Exception as e:
            return {"ok": False, "error": f"Errore completamento passkey: {str(e)}"}

    def start_passkey_authentication(self, email: str) -> Dict[str, Any]:
        """Inizia il flusso di autenticazione con passkey."""
        if not _check_fido2():
            return {"ok": False, "error": "WebAuthn non disponibile"}
        
        email = (email or "").strip().lower()
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM users WHERE email = ? AND passkey_enrolled = 1",
            (email,)
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"ok": False, "error": "Utente non ha passkey registrato"}
        
        user_id = row[0]
        
        try:
            server = self._get_fido2_server()
            if not server:
                conn.close()
                return {"ok": False, "error": "Server FIDO2 non configurato"}
            
            # Recupera i credential dell'utente
            cur.execute(
                "SELECT credential_id FROM webauthn_credentials WHERE user_id = ?",
                (user_id,)
            )
            credentials = []
            for cred_row in cur.fetchall():
                cred_id = base64.b64decode(cred_row[0])
                credentials.append(PublicKeyCredentialDescriptor(cred_id))
            
            auth_data, state = server.authenticate_begin(credentials)
            
            # Salva lo state challenge
            challenge_hash = state.challenge
            now = datetime.utcnow()
            expires_at = (now + timedelta(minutes=10)).isoformat()
            cur.execute(
                "INSERT INTO webauthn_challenges (user_id, challenge_hash, purpose, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, challenge_hash, "authentication", now.isoformat(), expires_at)
            )
            conn.commit()
            conn.close()
            
            options_json = json.dumps(auth_data, default=lambda o: o.__dict__ if hasattr(o, '__dict__') else str(o))
            return {"ok": True, "user_id": user_id, "options": options_json}
        except Exception as e:
            conn.close()
            return {"ok": False, "error": f"Errore autenticazione passkey: {str(e)}"}

    def complete_passkey_authentication(self, user_id: str, response_json: str) -> Dict[str, Any]:
        """Completa l'autenticazione con passkey."""
        if not _check_fido2():
            return {"ok": False, "error": "WebAuthn non disponibile"}
        
        try:
            server = self._get_fido2_server()
            if not server:
                return {"ok": False, "error": "Server FIDO2 non configurato"}
            
            conn = self._conn()
            cur = conn.cursor()
            
            # Recupera il challenge
            cur.execute(
                "SELECT challenge_hash FROM webauthn_challenges WHERE user_id = ? AND purpose = ? AND expires_at > ? ORDER BY created_at DESC LIMIT 1",
                (user_id, "authentication", datetime.utcnow().isoformat())
            )
            row = cur.fetchone()
            if not row:
                conn.close()
                return {"ok": False, "error": "Challenge non trovato o scaduto"}
            
            response_data = json.loads(response_json)
            auth_result = server.authenticate_complete(
                bytes.fromhex(row[0]),  # challenge_hash
                response_data
            )
            
            # Aggiorna il timestamp dell'uso del credential
            cred_id = base64.b64encode(auth_result.credential_id).decode()
            cur.execute(
                "UPDATE webauthn_credentials SET last_used_at = ? WHERE credential_id = ?",
                (datetime.utcnow().isoformat(), cred_id)
            )
            
            # Crea sessione
            cur.execute("UPDATE users SET last_login = ? WHERE id = ?", (datetime.utcnow().isoformat(), user_id))
            conn.commit()
            
            token_info = self._create_session(cur, user_id)
            conn.commit()
            conn.close()
            
            return {"ok": True, "user_id": user_id, **token_info}
        except Exception as e:
            return {"ok": False, "error": f"Errore autenticazione passkey: {str(e)}"}

    def has_passkey(self, user_id: str) -> bool:
        """Controlla se l'utente ha un passkey registrato."""
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("SELECT passkey_enrolled FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        return bool(row and row[0])




if __name__ == "__main__":
    um = UserManager()
    print("Users & sessions tables ready at:", DB_PATH)
    email = "demo@example.com"
    pwd = "DemoPass123!"
    res = um.register(email, pwd, username="demo")
    if not res.get("ok") and "già registrata" not in res.get("error", ""):
        print("Register error:", res)
    auth = um.authenticate(email, pwd)
    print("Auth:", auth)
    if auth.get("ok"):
        chk = um.validate_session(auth["token"])  # type: ignore[index]
        print("Session valid:", chk)
