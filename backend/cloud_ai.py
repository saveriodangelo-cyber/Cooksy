from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from backend.cloud_settings import load_settings
from backend.utils import project_root


class CloudAIError(RuntimeError):
    pass


def _shared_openai_config() -> Tuple[str, str, bool]:
    # Prova a leggere dal file config
    config_file = project_root() / "data" / "config" / "shared_openai.json"
    if config_file.exists():
        try:
            data = json.loads(config_file.read_text(encoding="utf-8", errors="replace"))
            if isinstance(data, dict):
                key = str(data.get("api_key", "")).strip()
                model = str(data.get("model", "gpt-4.1-mini")).strip() or "gpt-4.1-mini"
                enabled = bool(data.get("enabled", True)) and bool(key)
                if key:
                    return key, model, enabled
        except Exception:
            pass
    
    # Fallback: env vars
    key = (os.environ.get("RICETTEPDF_SHARED_OPENAI_KEY") or os.environ.get("COOKSY_SHARED_OPENAI_KEY") or "").strip()
    model = (os.environ.get("RICETTEPDF_SHARED_OPENAI_MODEL") or "gpt-4.1-mini").strip() or "gpt-4.1-mini"
    enabled_flag = str(os.environ.get("RICETTEPDF_SHARED_OPENAI_ENABLED", "1")).lower().strip()
    enabled = bool(key) and enabled_flag not in {"0", "false", "no", "off"}
    return key, model, enabled


def shared_openai_available() -> bool:
    key, _model, enabled = _shared_openai_config()
    return bool(key) and bool(enabled)


def _ensure_https(url: str, provider: str) -> None:
    if not str(url).lower().startswith("https://"):
        raise CloudAIError(f"Endpoint {provider} non sicuro: richiede HTTPS")


def _http_json(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: int = 45) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        # maschera eventuali chiavi nel body
        masked = body.replace(headers.get("Authorization", ""), "***") if body else ""
        raise CloudAIError(f"HTTP {e.code}: {masked[:500]}")
    except urllib.error.URLError as e:
        raise CloudAIError(f"Connessione fallita: {e}")
    except Exception as e:
        raise CloudAIError(f"{type(e).__name__}: {e}")


def _openai_complete(api_key: str, model: str, prompt: str) -> str:
    url = os.environ.get("COOKSY_OPENAI_URL", "https://api.openai.com/v1/responses")
    _ensure_https(url, "OpenAI")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "input": prompt,
        "temperature": 0.2,
        "max_output_tokens": 1600,
        "text": {"format": {"type": "json_object"}},
        "store": False,
    }
    data = _http_json(url, headers, payload, timeout=60)

    # Responses API: output_text spesso è disponibile; in alternativa, cerchiamo nei blocchi.
    if isinstance(data, dict):
        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text
        out = data.get("output")
        if isinstance(out, list):
            texts: List[str] = []
            for item in out:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") in ("output_text", "text"):
                            t = c.get("text")
                            if isinstance(t, str) and t.strip():
                                texts.append(t)
            if texts:
                return "\n".join(texts)

    raise CloudAIError("Risposta OpenAI non interpretabile")


def _openai_complete_with_fallback(api_key: str, model: str, prompt: str) -> Tuple[str, str]:
    tried: List[str] = []
    last_error: Optional[str] = None
    candidates = [model, "gpt-5.2", "gpt-5.1", "gpt-5", "gpt-4.1", "gpt-4.1-mini", "gpt-4o-mini", "gpt-4o"]
    for cand in candidates:
        if not cand:
            continue
        if cand in tried:
            continue
        tried.append(cand)
        try:
            return _openai_complete(api_key, cand, prompt), cand
        except CloudAIError as e:
            last_error = str(e)
    raise CloudAIError(last_error or "Errore OpenAI")


def _openai_complete_patch(api_key: str, model: str, prompt: str) -> Tuple[Dict[str, Any], str]:
    tried: List[str] = []
    last_error: Optional[str] = None
    candidates = [model, "gpt-5.2", "gpt-5.1", "gpt-5", "gpt-4.1", "gpt-4.1-mini", "gpt-4o-mini", "gpt-4o"]
    for cand in candidates:
        if not cand:
            continue
        if cand in tried:
            continue
        tried.append(cand)
        try:
            out = _openai_complete(api_key, cand, prompt)
        except CloudAIError as e:
            last_error = str(e)
            continue
        patch = _parse_patch(out)
        if patch:
            return patch, cand
        last_error = "Risposta OpenAI vuota o JSON non valido"
    raise CloudAIError(last_error or "Errore OpenAI")


def _gemini_complete(api_key: str, model: str, prompt: str) -> str:
    # Gemini Generative Language API
    base = os.environ.get("COOKSY_GEMINI_URL", "https://generativelanguage.googleapis.com")
    # v1beta è quello più diffuso nei quickstart
    url = f"{base}/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 800},
    }
    data = _http_json(url, headers, payload, timeout=60)

    # Estrai testo
    try:
        candidates = data.get("candidates")
        if isinstance(candidates, list) and candidates:
            content = candidates[0].get("content")
            if isinstance(content, dict):
                parts = content.get("parts")
                if isinstance(parts, list):
                    texts: List[str] = [str(p.get("text")) for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str)]
                    if texts:
                        return "\n".join(texts)
    except Exception:
        pass

    raise CloudAIError("Risposta Gemini non interpretabile")


def _build_prompt(recipe: Dict[str, Any], missing: Dict[str, Any]) -> str:
    # Prompt volutamente conservativo: chiediamo patch JSON e canonical names.
    schema = {
        "title": "string|null",
        "servings": "int|null",
        "difficulty": "bassa|media|alta|null",
        "prep_time_min": "int|null",
        "cook_time_min": "int|null",
        "wine_pairing": "string|null",
        "storage": "string|null",
        "plating": "string|null",
        "notes": "string|null",
        "ingredients": [
            {"orig": "string", "name_db": "string|null"}
        ],
        "warnings": ["string"],
    }

    return (
        "Sei un assistente per completare schede ricetta.\n"
        "Ricevi una ricetta già estratta (JSON) e una lista di campi mancanti.\n"
        "OBIETTIVO: restituisci SOLO un JSON valido che rispetta lo schema richiesto.\n"
        "REGOLE IMPORTANTI:\n"
        "- Non cambiare campi già valorizzati nella ricetta.\n"
        "- Non inventare prezzi o valori nutrizionali.\n"
        "- Per gli ingredienti, proponi al massimo un 'name_db' (nome canonico) per migliorare il match nei database locali.\n"
        "- Se non sei sicuro, lascia null e aggiungi una nota in warnings.\n\n"
        f"SCHEMA OUTPUT (esempio tipi): {json.dumps(schema, ensure_ascii=False)}\n\n"
        f"MISSING: {json.dumps(missing, ensure_ascii=False)}\n\n"
        f"RICETTA: {json.dumps(recipe, ensure_ascii=False)[:12000]}\n"
    )


def _build_prompt_missing(recipe: Dict[str, Any], missing_fields: Any, source_text: str) -> str:
    required_keys = [
        "titolo",
        "ingredienti_blocco",
        "porzioni",
        "tempo_dettaglio",
        "difficolta",
        "procedimento_blocco",
        "conservazione",
        "categoria",
        "vegetariano flag",
        "diete",
        "note errori",
        "vino descrizione",
        "vino temperatura servizio",
        "vino regione",
        "vino annata",
        "vino motivo annata",
        "allergeni elenco",
        "attrezzature specifiche",
        "attrezzature generiche",
        "attrezzature semplici",
        "attrezzature professionali",
        "attrezzature pasticceria",
        "presentazione impiattamento",
        "ingredienti_dettaglio",
        "stagionalita",
        "spesa totale acquisto",
        "spesa totale ricetta",
        "spesa per porzione",
        "energia 100g",
        "energia totale",
        "carboidrati totali 100g",
        "carboidrati totali totale",
        "di cui zuccheri 100g",
        "di cui zuccheri totale",
        "grassi totali 100g",
        "grassi totali totale",
        "di cui saturi 100g",
        "di cui saturi totale",
        "monoinsaturi 100g",
        "monoinsaturi totale",
        "polinsaturi 100g",
        "polinsaturi totale",
        "proteine totali 100g",
        "proteine totali totale",
        "colesterolo totale 100g",
        "colesterolo totale totale",
        "fibre 100g",
        "fibre totale",
        "sodio 100g",
        "sodio totale",
    ]

    src = (source_text or "").strip()
    if len(src) > 6000:
        src = src[:6000] + "\n...[TRONCATO]"

    keys_json = json.dumps(required_keys, ensure_ascii=False)
    missing_json = json.dumps(missing_fields or [], ensure_ascii=False)
    recipe_json = json.dumps(recipe, ensure_ascii=False)[:12000]

    return (
        "Sei un assistente tecnico di cucina e nutrizione per un Istituto Alberghiero.\n"
        "Devi completare e sistemare i dati di una scheda tecnica di ricetta per gli studenti.\n\n"
        "Dati di partenza (possono essere incompleti o disordinati):\n"
        f"{src}\n\n"
        "RICETTA CORRENTE (JSON estratto):\n"
        f"{recipe_json}\n\n"
        f"CAMPI MANCANTI: {missing_json}\n\n"
        "COMPITI:\n\n"
        "STRUTTURA RICETTA (testo)\n"
        "Mantieni il titolo coerente con il piatto.\n"
        "'ingredienti_blocco': elenco strutturato, un ingrediente per riga, con quantita e unita (es. \"Cipolla 50 g\").\n"
        "- In 'ingredienti_blocco' NON inserire prezzi, allergeni, note, righe tipo \"prezzi aggiornati\", o frasi non-ingrediente.\n"
        "'tempo_dettaglio': stringa con tempi di preparazione, cottura e totale (es. \"Prep 10 min, Cottura 20 min, Tot 30 min\").\n"
        "'procedimento_blocco': sequenza di passaggi NUMERATI (1., 2., 3., ...), uno per riga, con frasi brevi e operative, tono semplice e imperativo rivolto a studenti di Istituto Alberghiero (es. \"Tagliare...\", \"Cuocere...\").\n"
        "'categoria': una tra Antipasto, Primo, Secondo, Piatto unico, Dessert.\n"
        "'conservazione': come conservare il piatto finito (frigo, giorni, ecc.).\n"
        "'vegetariano flag': \"Si\" o \"No\".\n"
        "'diete': elenco delle diete compatibili, separato da virgole, scegliendo SOLO tra:\n"
        "- Dieta vegetariana, Dieta vegana, Dieta plant-based, Dieta flexitariana, Dieta pescetariana,\n"
        "- Dieta senza glutine (per celiachia), Dieta ipocalorica, Dieta ipercalorica, Dieta per diabetici,\n"
        "- Dieta per ipertensione, Dieta per reflusso gastroesofageo,\n"
        "- Dieta halal, Dieta kosher, Dieta induista, Dieta buddhista,\n"
        "- Dieta mediterranea, Dieta chetogenica.\n"
        "Compila SEMPRE il campo 'diete' con tutte le compatibilita plausibili.\n"
        "'note errori': al massimo una riga breve, tecnica, per il docente.\n"
        "2. ALLERGENI\n"
        "'allergeni elenco': elenco in italiano degli allergeni presenti nel piatto, separati da virgole, usando le categorie del Reg. UE.\n"
        "3. ABBINAMENTO VINO\n"
        "'vino descrizione': breve descrizione di un abbinamento vino realistico (tipo, denominazione).\n"
        "'vino temperatura servizio': temperatura di servizio in gradi (es. \"10-12\").\n"
        "'vino regione': regione di provenienza.\n"
        "'vino annata': annata consigliata (es. \"2019\").\n"
        "'vino motivo annata': breve motivo tecnico del perche l'annata e adatta.\n"
        "4. PREZZO DEL PIATTO (stime)\n"
        "'ingredienti_dettaglio': righe nel formato \"Ingrediente | Scarto% | Peso min. acquisto | Prezzo kg/ud | Quantita usata | Prezzo acquisto | Prezzo calcolato\".\n"
        "- Scarto%: percentuale di scarto del singolo ingrediente (0-60). Usa 0 SOLO per ingredienti gia puliti/confezionati; altrimenti stima realistica.\n"
        "'spesa totale acquisto': costo indicativo totale per acquistare gli ingredienti nelle quantita minime vendute (EUR/ricetta), es. \"12.50\" (solo numero in stringa, 2 decimali, senza simbolo).\n"
        "'spesa totale ricetta': costo indicativo della sola quantita effettivamente utilizzata nella ricetta (EUR/ricetta), es. \"8.30\".\n"
        "'spesa per porzione': spesa totale ricetta divisa per le porzioni, es. \"1.04\".\n"
        "5. VALORI NUTRIZIONALI (stime plausibili)\n"
        "'energia 100g', 'energia totale' (Kcal)\n"
        "'carboidrati totali 100g', 'carboidrati totali totale' (g)\n"
        "'di cui zuccheri 100g', 'di cui zuccheri totale' (g)\n"
        "'grassi totali 100g', 'grassi totali totale' (g)\n"
        "'di cui saturi 100g', 'di cui saturi totale' (g)\n"
        "'monoinsaturi 100g', 'monoinsaturi totale' (g)\n"
        "'polinsaturi 100g', 'polinsaturi totale' (g)\n"
        "'proteine totali 100g', 'proteine totali totale' (g)\n"
        "'colesterolo totale 100g', 'colesterolo totale totale' (mg)\n"
        "'fibre 100g', 'fibre totale' (g)\n"
        "'sodio 100g', 'sodio totale' (mg)\n"
        "6. ATTREZZATURE E IMPIATTAMENTO\n"
        "'attrezzature semplici': elenco puntato (una per riga) delle attrezzature di base.\n"
        "'attrezzature professionali': elenco puntato (una per riga) delle attrezzature PROFESSIONALI o non comuni usate per questa ricetta.\n"
        "'attrezzature pasticceria': elenco puntato (una per riga) delle attrezzature di pasticceria.\n"
        "'attrezzature specifiche': copia di 'attrezzature professionali'.\n"
        "'attrezzature generiche': copia di 'attrezzature semplici'.\n"
        "'presentazione impiattamento': 2-3 frasi brevi che descrivono tipo di piatto/supporto, decorazioni essenziali, temperatura e ordine di impiattamento.\n\n"
        "7. STAGIONALITA\n"
        "'stagionalita': periodo consigliato (mesi o stagione), con breve motivazione.\n\n"
        "Linee guida per i NUMERI:\n"
        "- Devono essere plausibili rispetto agli ingredienti.\n"
        "- Scrivili come STRINGHE con solo numeri e al massimo 1 decimale (o interi), punto come separatore decimale.\n"
        "- Non aggiungere unita o simboli (Kcal, g, mg, EUR) nei valori.\n\n"
        "IMPORTANTE:\n"
        "- Non riscrivere il contenuto: puoi solo pulire numerazioni/bullet, spazi doppi, duplicati e righe vuote.\n"
        "- Se un dato e' presente nel testo ma nel campo sbagliato, spostalo nel campo corretto senza riscriverlo.\n"
        "- Se un campo e' gia presente nella ricetta corrente, NON modificarlo: completa solo i campi mancanti.\n"
        "- Se un valore manca nel testo, stima in modo realistico SOLO per i campi in CAMPI MANCANTI.\n"
        "- Non restituire mai 'non disponibile'.\n"
        "- Non usare mai 'None' o 'null': inserisci sempre numeri o stringhe valide.\n"
        f"Devi restituire un JSON con ESATTAMENTE queste chiavi: {keys_json}\n"
        "Per ciascuna chiave, il valore deve essere una stringa.\n"
    )



def _parse_patch(text: str) -> Dict[str, Any]:
    # prova a trovare un JSON nel testo
    t = (text or "").strip()
    if not t:
        return {}

    # se è già JSON puro
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass

    # estrai tra prima { e ultima }
    try:
        a = t.find("{")
        b = t.rfind("}")
        if a >= 0 and b > a:
            obj = json.loads(t[a : b + 1])
            return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}

    return {}


def cloud_complete_recipe(recipe: Dict[str, Any], missing: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
    """Ritorna (used, patch, provider_used)."""
    settings = load_settings()
    if not settings.get("enabled"):
        return False, {}, "offline"

    provider = str(settings.get("provider") or "auto").lower().strip()
    if provider == "offline":
        return False, {}, "offline"

    openai_key = str((settings.get("openai") or {}).get("api_key") or "").strip()
    gemini_key = str((settings.get("gemini") or {}).get("api_key") or "").strip()

    provider_used = provider
    if provider == "auto":
        if openai_key:
            provider_used = "openai"
        elif gemini_key:
            provider_used = "gemini"
        else:
            return False, {}, "offline"

    prompt = _build_prompt(recipe, missing)

    if provider_used == "openai":
        if not openai_key:
            return False, {}, "openai"
        model = str((settings.get("openai") or {}).get("model") or "gpt-4.1-mini")
        patch, model_used = _openai_complete_patch(openai_key, model, prompt)
        return True, patch, f"openai:{model_used}"

    if provider_used == "gemini":
        if not gemini_key:
            return False, {}, "gemini"
        model = str((settings.get("gemini") or {}).get("model") or "gemini-1.5-flash")
        out = _gemini_complete(gemini_key, model, prompt)
        patch = _parse_patch(out)
        return True, patch, "gemini"

    return False, {}, "offline"


def complete_missing_fields(
    recipe: Dict[str, Any],
    missing_fields: Any,
    source_text: str = "",
    *,
    subscription_tier: str = "",
    allow_shared: bool = False,
) -> Tuple[bool, Dict[str, Any], str]:
    """Completa campi mancanti con Cloud AI (OpenAI/Gemini via settings UI).

    `allow_shared` abilita l'uso di una chiave OpenAI condivisa via env
    (RICETTEPDF_SHARED_OPENAI_KEY) per gli abbonati a pagamento.
    """
    settings = load_settings()
    shared_key, shared_model, shared_enabled = _shared_openai_config()
    tier = str(subscription_tier or "").lower().strip()
    tier_allows_shared = tier not in {"", "free", "starter"}
    use_shared = bool(allow_shared and shared_enabled and tier_allows_shared)

    if not settings.get("enabled") and not use_shared:
        return False, {}, "offline"

    provider = str(settings.get("provider") or "auto").lower().strip()
    if provider == "offline" and not use_shared:
        return False, {}, "offline"

    openai_key = str((settings.get("openai") or {}).get("api_key") or "").strip()
    gemini_key = str((settings.get("gemini") or {}).get("api_key") or "").strip()

    provider_used = provider
    if use_shared:
        openai_key = shared_key
        provider_used = "openai" if provider in {"auto", "openai", "shared"} else provider

    if provider_used == "auto":
        if openai_key:
            provider_used = "openai"
        elif gemini_key:
            provider_used = "gemini"
        else:
            return False, {}, "offline"

    if provider_used == "gemini" and not gemini_key and use_shared and openai_key:
        provider_used = "openai"

    prompt = _build_prompt_missing(recipe, missing_fields, source_text)

    if provider_used == "openai":
        if not openai_key:
            return False, {}, "openai"
        model = str((settings.get("openai") or {}).get("model") or "gpt-4.1-mini")
        if use_shared:
            model = shared_model or model
        patch, model_used = _openai_complete_patch(openai_key, model, prompt)
        return True, patch, ""

    if provider_used == "gemini":
        if not gemini_key:
            return False, {}, "gemini"
        model = str((settings.get("gemini") or {}).get("model") or "gemini-1.5-flash")
        out = _gemini_complete(gemini_key, model, prompt)
        patch = _parse_patch(out)
        return True, patch, "gemini"

    return False, {}, "offline"


def test_cloud_connection() -> Dict[str, Any]:
    """Test leggero: verifica che almeno un provider risponda."""
    settings = load_settings()
    _shared_key, _shared_model, shared_enabled = _shared_openai_config()
    if not settings.get("enabled") and not shared_enabled:
        return {"ok": False, "error": "Cloud AI disabilitata"}

    dummy_recipe = {"title": "Test", "ingredients": [{"name": "zucchero", "qty": 100, "unit": "g"}], "steps": [{"text": "Mescola"}]}
    missing = {"fields": ["wine_pairing"], "missing_prices": [], "missing_nutrition": []}

    try:
        used, patch, prov = complete_missing_fields(
            dummy_recipe,
            missing.get("fields") or missing,
            subscription_tier="pro",
            allow_shared=bool(shared_enabled),
        )
        if not used:
            return {"ok": False, "error": "Nessuna chiave disponibile (OpenAI/Gemini) o provider offline", "provider": prov}
        return {"ok": True, "provider": prov, "patch_keys": list(patch.keys())}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
