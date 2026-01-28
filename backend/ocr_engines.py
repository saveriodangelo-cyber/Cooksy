# FILE: backend/ocr_engines.py
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError


ProgressCb = Optional[Callable[[int, str], None]]


_UNITS = ("g", "kg", "ml", "l", "cl", "dl", "mg", "pz", "gr", "lt")
_RE_UNIT_HIT = re.compile(r"\b(" + "|".join(map(re.escape, _UNITS)) + r")\b", re.IGNORECASE)
_RE_NUM = re.compile(r"\d")


def _score_text(text: str) -> int:
    if not text:
        return 0
    t = text.strip()
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if not lines:
        return 0

    words = re.findall(r"[A-Za-zÀ-ÿ]{3,}", t)
    useful_words = len(words)

    nums = len(_RE_NUM.findall(t))
    unit_hits = len(_RE_UNIT_HIT.findall(t))

    # penalità "spazzatura": troppe righe cortissime
    short_lines = sum(1 for ln in lines if len(ln) <= 2)
    penalty = short_lines * 3

    return useful_words + (nums * 2) + (unit_hits * 6) - penalty


@dataclass(slots=True)
class EngineResult:
    name: str
    available: bool
    ok: bool
    error: Optional[str]
    time_sec: float
    score: int
    text: str


def _run_with_timeout(fn: Callable[[], str], timeout_s: float) -> Tuple[bool, str, Optional[str], float]:
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn)
        try:
            text = fut.result(timeout=timeout_s)
            return True, text, None, time.perf_counter() - start
        except FuturesTimeoutError:
            return False, "", f"timeout>{timeout_s}s", time.perf_counter() - start
        except Exception as e:
            return False, "", str(e), time.perf_counter() - start


def _tesseract_ocr(image_paths: List[str], lang: str) -> str:
    import pytesseract  # type: ignore
    from PIL import Image  # pillow è tipicamente richiesto insieme a pytesseract

    def process_image(path: str) -> str:
        img = Image.open(path)
        return pytesseract.image_to_string(img, lang=lang)
    
    # Processamento parallelo se più immagini
    if len(image_paths) > 1:
        with ThreadPoolExecutor(max_workers=min(4, len(image_paths))) as executor:
            parts = list(executor.map(process_image, image_paths))
    else:
        parts = [process_image(p) for p in image_paths]
    
    return "\n".join(parts).strip()


def _easyocr_ocr(image_paths: List[str], lang: str) -> str:
    import easyocr  # type: ignore

    # easyocr vuole lista lingue tipo ["it"]
    langs = ["it"] if lang.lower().startswith("it") else [lang]
    reader = easyocr.Reader(langs, gpu=False)
    
    def process_image(path: str) -> str:
        result = reader.readtext(path, detail=0)
        return "\n".join(result).strip()
    
    # Processamento parallelo se più immagini
    if len(image_paths) > 1:
        with ThreadPoolExecutor(max_workers=min(4, len(image_paths))) as executor:
            parts = list(executor.map(process_image, image_paths))
        return "\n".join(parts).strip()
    
    # Fallback originale per singola immagine
    parts: List[str] = []
    for p in image_paths:
        out = reader.readtext(p, detail=0, paragraph=True)
        if isinstance(out, list):
            parts.append("\n".join(map(str, out)))
        else:
            parts.append(str(out))
    return "\n".join(parts).strip()


def _paddleocr_ocr(image_paths: List[str], lang: str) -> str:
    from paddleocr import PaddleOCR  # type: ignore

    ocr = PaddleOCR(use_angle_cls=True, lang="it")
    parts: List[str] = []
    for p in image_paths:
        res = ocr.ocr(p, cls=True)
        # res è una struttura annidata; estraiamo testo in modo robusto
        lines: List[str] = []
        if isinstance(res, list):
            for block in res:
                if isinstance(block, list):
                    for item in block:
                        if isinstance(item, list) and len(item) >= 2:
                            info = item[1]
                            if isinstance(info, (list, tuple)) and info:
                                lines.append(str(info[0]))
        parts.append("\n".join(lines))
    return "\n".join(parts).strip()


def _rapidocr_ocr(image_paths: List[str], lang: str) -> str:
    from rapidocr_onnxruntime import RapidOCR  # type: ignore

    ocr = RapidOCR()
    parts: List[str] = []
    for p in image_paths:
        result, _ = ocr(p)
        lines: List[str] = []
        if isinstance(result, list):
            for item in result:
                # item: (box, text, score) oppure simile
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    lines.append(str(item[1]))
        parts.append("\n".join(lines))
    return "\n".join(parts).strip()


def ocr_images_combined(
    image_paths: List[str],
    lang: str = "ita",
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    OCR multi-motore con scoring e fallback.
    Nessuna dipendenza è obbligatoria: se manca un motore, viene saltato.
    Timeout: se un motore impiega troppo, lo abortiamo (thread timeout) e passiamo oltre.

    Ritorna: (best_text, report)
    """
    report: Dict[str, Any] = {"engines": []}
    engines: List[Tuple[str, Callable[[], str]]] = []

    # registra motori disponibili (se import fallisce, li segniamo in report)
    def try_add(name: str, fn_builder: Callable[[], Callable[[], str]]) -> None:
        try:
            fn = fn_builder()
            engines.append((name, fn))
        except Exception as e:
            report["engines"].append(
                {
                    "name": name,
                    "available": False,
                    "ok": False,
                    "error": str(e),
                    "time_sec": 0.0,
                    "score": 0,
                }
            )

    try_add("tesseract", lambda: (lambda: _tesseract_ocr(image_paths, lang)))
    try_add("easyocr", lambda: (lambda: _easyocr_ocr(image_paths, lang)))
    try_add("paddleocr", lambda: (lambda: _paddleocr_ocr(image_paths, lang)))
    try_add("rapidocr", lambda: (lambda: _rapidocr_ocr(image_paths, lang)))

    results: List[EngineResult] = []
    timeout_per_engine_s = 45.0

    for i, (name, fn) in enumerate(engines, start=1):
        if progress_cb:
            progress_cb(int(5 + (i * 20)), f"OCR: {name}…")

        ok, text, err, tsec = _run_with_timeout(fn, timeout_s=timeout_per_engine_s)
        score = _score_text(text) if ok else 0

        results.append(
            EngineResult(
                name=name,
                available=True,
                ok=ok,
                error=err,
                time_sec=float(tsec),
                score=int(score),
                text=text if ok else "",
            )
        )

        report["engines"].append(
            {
                "name": name,
                "available": True,
                "ok": ok,
                "error": err,
                "time_sec": float(tsec),
                "score": int(score),
            }
        )

    # scegli il migliore
    best = max(results, key=lambda r: r.score, default=None)
    best_text = best.text if best and best.ok else ""

    report["selected"] = best.name if best else None
    report["selected_score"] = best.score if best else 0

    if progress_cb:
        progress_cb(95, "OCR completato")

    return best_text, report
