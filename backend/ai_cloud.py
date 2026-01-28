"""Cloud AI (optional) per completare/normalizzare dati ricetta.

Nessuna dipendenza esterna: solo stdlib (urllib).

Uso previsto (pipeline):
1) Dopo parsing + integrazioni locali, se risultano campi mancanti (soprattutto ingredienti senza match nei DB),
   chiediamo al cloud una *patch* JSON.
2) Applichiamo la patch SENZA sovrascrivere campi già popolati.
3) Se la patch propone nomi canonici per ingredienti mancanti, li salviamo in `matched_name` dentro gli ingredienti.
   I motori `price_engine` e `nutrition_engine` useranno `matched_name` preferendolo a `name` per il matching.

Provider supportati:
- OpenAI (Responses API): https://api.openai.com/v1/responses
- Gemini (GenerateContent): https://generativelanguage.googleapis.com/v1beta/{model=models/*}:generateContent

Configurazione (solo env vars):
- OPENAI_API_KEY  -> abilita OpenAI
- GEMINI_API_KEY oppure GOOGLE_API_KEY -> abilita Gemini
- RICETTEPDF_CLOUD_PROVIDER = "openai" | "gemini" (opzionale)
- RICETTEPDF_CLOUD_AI = 0/1 (opzionale, default 1)
- RICETTEPDF_OPENAI_MODEL (default: gpt-4.1-mini)
- RICETTEPDF_GEMINI_MODEL (default: models/gemini-1.5-flash)

Nota: se più chiavi sono presenti e non si imposta RICETTEPDF_CLOUD_PROVIDER, preferiamo OpenAI.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


def cloud_enabled() -> bool:
    v = str(os.environ.get("RICETTEPDF_CLOUD_AI", "1")).strip().lower()
    return v not in ("0", "false", "no", "off")


def _has_openai() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _has_gemini() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def pick_provider() -> Optional[str]:
    if not cloud_enabled():
        return None

    pref = str(os.environ.get("RICETTEPDF_CLOUD_PROVIDER", "")).strip().lower()
    if pref in ("openai", "gemini"):
        if pref == "openai" and _has_openai():
            return "openai"
        if pref == "gemini" and _has_gemini():
            return "gemini"
        return None

    # auto
    if _has_openai():
        return "openai"
    if _has_gemini():
        return "gemini"
    return None


def should_call_cloud(recipe: Dict[str, Any], missing_fields: Optional[List[str]] = None) -> bool:
    """Heuristic: chiamiamo cloud solo se c'è qualcosa da completare davvero."""
    if pick_provider() is None:
        return False

    mf = missing_fields or []
    if any(x in mf for x in ("title", "servings", "difficulty", "time", "wine", "ingredients", "steps", "nutrition", "costs")):
        return True

    # segnali da integrazioni locali
    try:
        cs = recipe.get("cost_summary") or {}
        if isinstance(cs, dict) and cs.get("missing_prices"):
            return True
    except Exception:
        pass

    try:
        n = recipe.get("nutrition") or {}
        if isinstance(n, dict) and n.get("missing_nutrition"):
            return True
    except Exception:
        pass

    # metadati vuoti
    for k in ("difficulty", "difficolta", "wine", "vino", "prep_time", "cook_time", "rest_time"):
        v = recipe.get(k)
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            return True

    return False


def _scrub_credentials(text: str) -> str:
    """Remove sensitive credentials from error messages and logs."""
    if not text:
        return text
    # Remove Bearer tokens
    text = re.sub(r'Bearer\s+[a-zA-Z0-9._\-]+', 'Bearer ***REDACTED***', text)
    # Remove API keys (key=..., key: "...", key: '...')
    text = re.sub(r'["\']?key["\']?\s*[:=]\s*["\']?[a-zA-Z0-9._\-/+=]+', 'key=***REDACTED***', text)
    # Remove x-goog-api-key headers
    text = re.sub(r'x-goog-api-key\s*[:=]\s*[a-zA-Z0-9._\-]+', 'x-goog-api-key=***REDACTED***', text)
    # Remove query string keys
    text = re.sub(r'\?key=[a-zA-Z0-9._\-/+=]+', '?key=***REDACTED***', text)
    return text


def _http_json(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: int = 45) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
            body = _scrub_credentials(body)
        except Exception:
            body = ""
        msg = body.strip() or f"HTTP {e.code}: {e.reason}"
        raise RuntimeError(msg)
    except Exception as e:
        raise RuntimeError(f"{type(e).__name__}: {e}")

    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}


def _extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Estrae un oggetto JSON dall'output del modello in modo robusto."""
    if not text:
        return None
    t = text.strip()
    # rimuovi code fences
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
        t = t.strip()

    # tentativo 1: parse diretto
    try:
        j = json.loads(t)
        return j if isinstance(j, dict) else None
    except Exception:
        pass

    # tentativo 2: cerca primo {...}
    m = re.search(r"\{[\s\S]*\}", t)
    if not m:
        return None
    chunk = m.group(0)
    try:
        j = json.loads(chunk)
        return j if isinstance(j, dict) else None
    except Exception:
        return None


def request_patch(
    recipe: Dict[str, Any],
    source_text: str,
    missing_fields: Optional[List[str]] = None,
    *,
    max_source_chars: int = 7000,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Chiama il provider cloud e ritorna (patch, meta)."""
    provider = pick_provider()
    meta: Dict[str, Any] = {"provider": provider}
    if provider is None:
        return None, meta

    # riduci contesto (evita token enormi)
    src = (source_text or "").strip()
    if len(src) > max_source_chars:
        src = src[:max_source_chars] + "\n...[TRONCATO]"

    # costruisci segnali di missing
    cs = recipe.get("cost_summary") if isinstance(recipe.get("cost_summary"), dict) else {}
    nu = recipe.get("nutrition") if isinstance(recipe.get("nutrition"), dict) else {}
    miss_prices = cs.get("missing_prices") if isinstance(cs, dict) else None
    miss_nutri = nu.get("missing_nutrition") if isinstance(nu, dict) else None

    prompt = {
        "goal": "Completa SOLO i dati mancanti di una ricetta italiana senza inventare numeri (prezzi/kcal).",
        "rules": [
            "Rispondi ESCLUSIVAMENTE con un JSON valido (niente testo extra).",
            "Non sovrascrivere campi già presenti: restituisci solo ciò che manca.",
            "Per ingredienti senza match in DB: proponi solo nomi canonici (matched_name) utili al matching, non prezzi/kcal.",
            "Se non sei sicuro, lascia il campo assente.",
        ],
        "missing_fields": missing_fields or [],
        "missing_prices": miss_prices or [],
        "missing_nutrition": miss_nutri or [],
        "recipe_current": recipe,
        "source_text": src,
        "output_schema": {
            "ingredient_name_hints": [
                {
                    "original": "ingrediente mancante (string)",
                    "matched_name": "nome canonico per DB (string)",
                    "confidence": 0.0,
                    "notes": "string opzionale",
                }
            ],
            "fill_fields": {
                "title": "string",
                "servings": 0,
                "difficulty": "facile|media|difficile",
                "prep_time_min": 0,
                "cook_time_min": 0,
                "rest_time_min": 0,
                "wine_pairing": "string",
                "notes": "string",
            },
        },
    }

    if provider == "openai":
        patch, meta2 = _call_openai(prompt)
        meta.update(meta2)
        return patch, meta
    if provider == "gemini":
        patch, meta2 = _call_gemini(prompt)
        meta.update(meta2)
        return patch, meta

    return None, meta


def _build_legacy_prompt_text(
    recipe: Dict[str, Any],
    missing_fields: Optional[List[str]],
    source_text: str,
) -> str:
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

    return (
        "Sei un assistente tecnico di cucina e nutrizione per un Istituto Alberghiero.\n"
        "Devi completare e sistemare i dati di una scheda tecnica di ricetta per gli studenti.\n\n"
        "Dati di partenza (possono essere incompleti o disordinati):\n"
        f"{source_text}\n\n"
        "RICETTA CORRENTE (JSON estratto):\n"
        f"{json.dumps(recipe, ensure_ascii=False)[:12000]}\n\n"
        f"CAMPI MANCANTI: {json.dumps(missing_fields or [], ensure_ascii=False)}\n\n"
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
        f"Devi restituire un JSON con ESATTAMENTE queste chiavi: {json.dumps(required_keys, ensure_ascii=False)}\n"
        "Per ciascuna chiave, il valore deve essere una stringa.\n"
    )


def request_full_recipe(
    recipe: Dict[str, Any],
    source_text: str,
    missing_fields: Optional[List[str]] = None,
    *,
    max_source_chars: int = 7000,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Chiede al cloud una ricetta completa (JSON), da usare per colmare i campi mancanti."""
    provider = pick_provider()
    meta: Dict[str, Any] = {"provider": provider}
    if provider is None:
        return None, meta

    src = (source_text or "").strip()
    if len(src) > max_source_chars:
        src = src[:max_source_chars] + "\n...[TRONCATO]"

    prompt = _build_legacy_prompt_text(recipe, missing_fields, src)


    if provider == "openai":
        patch, meta2 = _call_openai(prompt)
        meta.update(meta2)
        return patch, meta
    if provider == "gemini":
        patch, meta2 = _call_gemini(prompt)
        meta.update(meta2)
        return patch, meta

    return None, meta


def _call_openai(prompt_obj: Any) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    api_key = os.environ.get("OPENAI_API_KEY") or ""
    model = os.environ.get("RICETTEPDF_OPENAI_MODEL", "gpt-4.1-mini")
    url = "https://api.openai.com/v1/responses"

    prompt_text = prompt_obj if isinstance(prompt_obj, str) else json.dumps(prompt_obj, ensure_ascii=False)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    payload: Dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt_text}
                ],
            }
        ],
        "temperature": 0.2,
        "max_output_tokens": 900,
        "store": False,
        "text": {"format": {"type": "text"}},
    }

    meta: Dict[str, Any] = {"model": model, "endpoint": url}
    data = _http_json(url, payload, headers=headers, timeout=60)

    # estrai testo da output[]
    out_text = ""
    try:
        for item in data.get("output") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message":
                continue
            if item.get("role") != "assistant":
                continue
            for part in item.get("content") or []:
                if isinstance(part, dict) and part.get("type") == "output_text":
                    out_text += str(part.get("text") or "")
    except Exception:
        out_text = ""

    patch = _extract_json_from_text(out_text)
    meta["ok"] = bool(patch)
    return patch, meta


def _call_gemini(prompt_obj: Any) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    model = os.environ.get("RICETTEPDF_GEMINI_MODEL", "models/gemini-1.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent"

    prompt_text = prompt_obj if isinstance(prompt_obj, str) else json.dumps(prompt_obj, ensure_ascii=False)

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }
    payload: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt_text}],
            }
        ],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 900},
    }

    meta: Dict[str, Any] = {"model": model, "endpoint": ".../generateContent"}
    data = _http_json(url, payload, headers=headers, timeout=60)

    out_text = ""
    try:
        candidates = data.get("candidates") or []
        if isinstance(candidates, list) and candidates:
            c0 = candidates[0]
            if isinstance(c0, dict):
                content = c0.get("content") or {}
                parts = content.get("parts") or []
                for p in parts:
                    if isinstance(p, dict) and "text" in p:
                        out_text += str(p.get("text") or "")
    except Exception:
        out_text = ""

    patch = _extract_json_from_text(out_text)
    meta["ok"] = bool(patch)
    return patch, meta


def apply_patch(recipe: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Applica patch in-place. Ritorna un meta con contatori."""
    meta: Dict[str, Any] = {"applied_fields": 0, "applied_ingredient_hints": 0}

    if not isinstance(patch, dict):
        return meta

    # 1) ingredient_name_hints -> matched_name
    hints = patch.get("ingredient_name_hints")
    if isinstance(hints, list) and hints:
        # crea indice ingredienti della ricetta (per name)
        ings = recipe.get("ingredients")
        if isinstance(ings, list):
            for h in hints:
                if not isinstance(h, dict):
                    continue
                orig = str(h.get("original") or "").strip()
                mname = str(h.get("matched_name") or "").strip()
                if not orig or not mname:
                    continue
                # applica su ingredienti che compaiono come missing nel report o che matchano per sottostringa
                for ing in ings:
                    if not isinstance(ing, dict):
                        continue
                    cur_name = str(ing.get("name") or ing.get("nome") or "").strip()
                    if not cur_name:
                        continue
                    if cur_name.lower() == orig.lower() or orig.lower() in cur_name.lower():
                        if not (ing.get("matched_name") or "").strip():
                            ing["matched_name"] = mname
                            meta["applied_ingredient_hints"] += 1

    # 2) fill_fields: set solo se vuoti
    fill = patch.get("fill_fields")
    if isinstance(fill, dict) and fill:
        for k, v in fill.items():
            if v is None:
                continue
            existing = recipe.get(k)
            is_missing = existing is None or (isinstance(existing, str) and not existing.strip())
            if is_missing:
                recipe[k] = v
                meta["applied_fields"] += 1

    return meta
