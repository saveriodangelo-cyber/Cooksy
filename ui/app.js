(function () {
  // Debug logger minimale (solo console)
  const debugLog = (msg) => {
    try { console.log(msg); } catch (_) { /* no-op */ }
  };

  debugLog('[COOKSY] app.js loaded');
  document.addEventListener('DOMContentLoaded', () => debugLog('[COOKSY] DOM ready'));

  // ===== SECURITY: Global HTML Sanitization =====
  const escapeHtml = (str) => {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  };

  const sanitizeHtml = (html) => {
    return String(html)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  };

  // ===== SECURITY: CSRF Token Generation =====
  const csrfToken = (() => {
    try {
      const stored = sessionStorage.getItem('csrf_token');
      if (stored) return stored;
      const token = Array.from(crypto.getRandomValues(new Uint8Array(32)))
        .map(b => b.toString(16).padStart(2, '0'))
        .join('');
      sessionStorage.setItem('csrf_token', token);
      return token;
    } catch {
      // Fallback: genera un token valido (64 hex chars) quando crypto non disponibile
      const timestamp = Date.now().toString(16).padStart(16, '0');
      const fallback = timestamp + '0'.repeat(48); // Completa a 64 caratteri
      return fallback;
    }
  })();

  const el = (id) => document.getElementById(id);

  const btnPick = el('btnPick');
  const btnPickFolder = el('btnPickFolder');
  const btnClear = el('btnClear');
  const btnAnalyze = el('btnAnalyze');
  const btnExport = el('btnExport');
  const btnPrint = el('btnPrint');
  const btnArchiveSave = el('btnArchiveSave');
  const btnArchiveOpen = el('btnArchiveOpen');

  const btnOutDir = el('btnOutDir');
  const outDirLabel = el('outDirLabel');
  const selTemplate = el('selTemplate');
  const selPageSize = el('selPageSize');
  const btnTplPreview = el('btnTplPreview');
  const btnAiSettings = el('btnAiSettings');

  const authUserLabel = el('authUserLabel');
  const authQuotaLabel = el('authQuotaLabel');
  const btnLogin = el('btnLogin');
  const btnRegister = el('btnRegister');
  const btnLogout = el('btnLogout');
  const toastEl = el('toast');
  let toastTimer = null;

  const btnBatchStart = el('btnBatchStart');
  const btnBatchOpenOut = el('btnBatchOpenOut');
  const folderLabel = el('folderLabel');
  const batchCurrentFile = el('batchCurrentFile');

  let tplModal = null;
  let tplModalBackdrop = null;
  let tplModalTitle = null;
  let btnTplClose = null;
  let btnTplRefresh = null;
  let btnTplZoomIn = null;
  let btnTplZoomOut = null;
  let btnTplZoomReset = null;
  let tplZoomLabel = null;
  let tplFrame = null;
  let tplPreviewStage = null;
  let tplPreviewSheet = null;
  let tplPreviewSheetInner = null;
  let tplPreviewMargins = null;
  let tplPreviewLabel = null;
  let tplPreviewScale = null;
  let tplUiBound = false;
  let tplZoom = 1;
  let tplAutoFit = false;

  function resolveTplUi() {
    tplModal = el('tplModal') || el('tplPreviewModal');
    tplModalBackdrop = el('tplModalBackdrop') || el('tplPreviewBackdrop');
    tplModalTitle = el('tplModalTitle') || el('tplPreviewTitle');
    btnTplClose = el('btnTplClose') || el('btnTplPreviewClose');
    btnTplRefresh = el('btnTplRefresh') || el('btnTplPreviewRefresh');
    btnTplZoomIn = el('btnTplZoomIn');
    btnTplZoomOut = el('btnTplZoomOut');
    btnTplZoomReset = el('btnTplZoomReset');
    tplZoomLabel = el('tplZoomLabel');
    tplFrame = el('tplFrame') || el('tplPreviewFrame');
    tplPreviewStage = el('tplPreviewStage');
    tplPreviewSheet = el('tplPreviewSheet');
    tplPreviewSheetInner = el('tplPreviewSheetInner');
    tplPreviewMargins = el('tplPreviewMargins');
    tplPreviewLabel = el('tplPreviewLabel');
    tplPreviewScale = el('tplPreviewScale');
  }

  // ===== UI ZOOM CONTROLS (Mobile/Tablet Support) =====
  let uiZoomLevel = 1;
  const uiZoomMin = 0.8;
  const uiZoomMax = 2.0;
  const uiZoomStep = 0.1;

  const initUiZoom = () => {
    // Load saved zoom level
    const saved = localStorage.getItem('cooksy_ui_zoom');
    if (saved) {
      const z = parseFloat(saved);
      if (!isNaN(z) && z >= uiZoomMin && z <= uiZoomMax) {
        uiZoomLevel = z;
      }
    }
    applyUiZoom();

    // Bind zoom controls
    const btnZoomOut = el('btnZoomOut');
    const btnZoomIn = el('btnZoomIn');
    const btnZoomReset = el('btnZoomReset');
    const zoomLabel = el('zoomLabel');

    if (btnZoomOut) btnZoomOut.addEventListener('click', () => setUiZoom(uiZoomLevel - uiZoomStep));
    if (btnZoomIn) btnZoomIn.addEventListener('click', () => setUiZoom(uiZoomLevel + uiZoomStep));
    if (btnZoomReset) btnZoomReset.addEventListener('click', () => setUiZoom(1));

    // Keyboard shortcuts: Ctrl+Plus, Ctrl+Minus, Ctrl+0
    document.addEventListener('keydown', (ev) => {
      if (!ev.ctrlKey && !ev.metaKey) return;
      if (ev.key === '=' || ev.key === '+') {
        ev.preventDefault();
        setUiZoom(uiZoomLevel + uiZoomStep);
      } else if (ev.key === '-' || ev.key === '_') {
        ev.preventDefault();
        setUiZoom(uiZoomLevel - uiZoomStep);
      } else if (ev.key === '0') {
        ev.preventDefault();
        setUiZoom(1);
      }
    });

    // Show zoom controls on mobile/tablet
    detectMobileAndShowZoom();
    window.addEventListener('resize', detectMobileAndShowZoom);
  };

  const setUiZoom = (newZoom) => {
    newZoom = Math.max(uiZoomMin, Math.min(uiZoomMax, parseFloat(newZoom)));
    if (Math.abs(newZoom - uiZoomLevel) < 0.01) return; // No-op if nearly same
    uiZoomLevel = newZoom;
    localStorage.setItem('cooksy_ui_zoom', uiZoomLevel.toFixed(2));
    applyUiZoom();
  };

  const applyUiZoom = () => {
    const app = el('app') || document.querySelector('.app');
    if (!app) return;
    app.style.zoom = uiZoomLevel;

    // Update label
    const zoomLabel = el('zoomLabel');
    if (zoomLabel) {
      zoomLabel.textContent = `${Math.round(uiZoomLevel * 100)}%`;
    }
  };

  const detectMobileAndShowZoom = () => {
    const isMobile = window.innerWidth <= 900;
    const zoomControls = el('zoomControls');
    if (zoomControls) {
      if (isMobile) {
        zoomControls.classList.add('mobile');
      } else {
        zoomControls.classList.remove('mobile');
      }
    }
  };

  function bindTplUiOnce() {
    if (tplUiBound) return;
    resolveTplUi();
    if (!tplModal) return;
    if (btnTplClose) btnTplClose.addEventListener('click', hideTplModal);
    if (btnTplRefresh) btnTplRefresh.addEventListener('click', previewTemplateHtml);
    if (btnTplZoomIn) btnTplZoomIn.addEventListener('click', () => setTplZoom(tplZoom + 0.1));
    if (btnTplZoomOut) btnTplZoomOut.addEventListener('click', () => setTplZoom(tplZoom - 0.1));
    if (btnTplZoomReset) btnTplZoomReset.addEventListener('click', () => setTplZoom(1));
    if (tplPreviewStage) {
      tplPreviewStage.addEventListener('wheel', (ev) => {
        if (!ev.ctrlKey) return;
        ev.preventDefault();
        const dir = ev.deltaY > 0 ? -1 : 1;
        setTplZoom(tplZoom + dir * 0.1);
      }, { passive: false });
    }
    if (tplModalBackdrop) tplModalBackdrop.addEventListener('click', hideTplModal);
    tplUiBound = true;
  }

  const MM_PER_IN = 25.4;
  const PAGE_SPECS = {
    A3: { wMm: 297, hMm: 420, marginMm: 18 },
    A4: { wMm: 210, hMm: 297, marginMm: 15 },
    A5: { wMm: 148, hMm: 210, marginMm: 10 },
    A6: { wMm: 105, hMm: 148, marginMm: 8 },
    B5: { wMm: 176, hMm: 250, marginMm: 12 },
    LETTER: { wMm: 216, hMm: 279, marginMm: 15 },
    LEGAL: { wMm: 216, hMm: 356, marginMm: 15 },
    TABLOID: { wMm: 279, hMm: 432, marginMm: 18 },
    KDP_5X8: { wMm: 5 * MM_PER_IN, hMm: 8 * MM_PER_IN, marginMm: 0.45 * MM_PER_IN },
    KDP_5_5X8_5: { wMm: 5.5 * MM_PER_IN, hMm: 8.5 * MM_PER_IN, marginMm: 0.5 * MM_PER_IN },
    KDP_6X9: { wMm: 6 * MM_PER_IN, hMm: 9 * MM_PER_IN, marginMm: 0.5 * MM_PER_IN },
    KDP_7_5X9_25: { wMm: 7.5 * MM_PER_IN, hMm: 9.25 * MM_PER_IN, marginMm: 0.6 * MM_PER_IN },
    KDP_8_5X8_5: { wMm: 8.5 * MM_PER_IN, hMm: 8.5 * MM_PER_IN, marginMm: 0.6 * MM_PER_IN },
    KDP_8_5X11: { wMm: 8.5 * MM_PER_IN, hMm: 11 * MM_PER_IN, marginMm: 0.6 * MM_PER_IN },
  };

  function resolvePageSpec(pageSize) {
    const key = String(pageSize || 'A4').trim().toUpperCase();
    return { key, ...(PAGE_SPECS[key] || PAGE_SPECS.A4) };
  }

  function mmToPx(mm) {
    return (mm * 96) / MM_PER_IN;
  }

  function isTplModalVisible() {
    resolveTplUi();
    return !!(tplModal && !tplModal.classList.contains('hidden'));
  }

  function clamp(val, min, max) {
    return Math.max(min, Math.min(max, val));
  }

  function adjustPreviewTitleSize() {
    if (!prevTitle) return;
    const text = prevTitle.value || prevTitle.placeholder || '';
    let size = PREVIEW_TITLE_FONT_MAX;
    const width = prevTitle.clientWidth || (prevTitle.parentElement ? prevTitle.parentElement.clientWidth : 0);
    if (!width || !previewTitleCtx) {
      prevTitle.style.fontSize = `${size}px`;
      return;
    }
    const style = window.getComputedStyle(prevTitle);
    const weight = style.fontWeight || '900';
    const family = style.fontFamily || 'Segoe UI, Arial, sans-serif';
    while (size > PREVIEW_TITLE_FONT_MIN) {
      previewTitleCtx.font = `${weight} ${size}px ${family}`;
      const textWidth = previewTitleCtx.measureText(text).width + PREVIEW_TITLE_PADDING;
      if (textWidth <= width) break;
      size -= 1;
    }
    size = clamp(size, PREVIEW_TITLE_FONT_MIN, PREVIEW_TITLE_FONT_MAX);
    prevTitle.style.fontSize = `${size}px`;
  }

  function setTplZoom(val) {
    tplAutoFit = false;
    tplZoom = clamp(Number(val || 1), 0.35, 2.5);
    if (tplZoomLabel) tplZoomLabel.textContent = `${Math.round(tplZoom * 100)}%`;
    updateTplPreviewScale();
  }

  function buildPreviewPageCss(spec) {
    const w = Number(spec.wMm || 210);
    const h = Number(spec.hMm || 297);
    const m = Number(spec.marginMm || 15);
    return `
<style>
  @page { size: ${w}mm ${h}mm; margin: ${m}mm; }
  html, body { margin: 0; padding: ${m}mm; box-sizing: border-box; }
  *, *::before, *::after { box-sizing: border-box; }
</style>`;
  }

  function updateTplPreviewScale() {
    resolveTplUi();
    if (!tplPreviewStage || !tplPreviewSheet || !tplPreviewSheetInner) return;
    const pageKey = selPageSize ? selPageSize.value : 'A4';
    const spec = resolvePageSpec(pageKey);
    const a4 = resolvePageSpec('A4');
    const pagePxW = mmToPx(spec.wMm);
    const pagePxH = mmToPx(spec.hMm);
    const a4PxW = mmToPx(a4.wMm);

    let scale = tplZoom;
    if (!Number.isFinite(scale) || scale <= 0) scale = 1;

    let contentPxH = pagePxH;
    try {
      const doc = tplFrame?.contentDocument;
      const root = doc?.documentElement;
      const body = doc?.body;
      const rawH = Math.max(root?.scrollHeight || 0, body?.scrollHeight || 0);
      if (rawH && rawH > 0) contentPxH = Math.max(pagePxH, rawH);
    } catch (_) {
      contentPxH = pagePxH;
    }

    const stageW = tplPreviewStage?.clientWidth || 0;
    const stageH = tplPreviewStage?.clientHeight || 0;
    const availW = Math.max(0, stageW - 24);
    const availH = Math.max(0, stageH - 46);

    let fitScale = 1;
    if (availW && availH && pagePxW && contentPxH) {
      const fit = Math.min(availW / pagePxW, availH / contentPxH);
      if (Number.isFinite(fit) && fit > 0) fitScale = fit;
    }

    if (tplAutoFit && fitScale) {
      scale = Math.min(scale, fitScale);
    }
    scale = clamp(scale, 0.35, 2.5);

    const scaledW = pagePxW * scale;
    const scaledH = contentPxH * scale;
    tplPreviewSheet.style.width = `${scaledW}px`;
    tplPreviewSheet.style.height = `${scaledH}px`;
    tplPreviewSheetInner.style.width = `${pagePxW}px`;
    tplPreviewSheetInner.style.height = `${contentPxH}px`;
    tplPreviewSheetInner.style.transform = `scale(${scale})`;
    tplPreviewSheetInner.style.transformOrigin = 'top left';

    if (tplPreviewMargins) {
      const marginPx = mmToPx(spec.marginMm);
      tplPreviewMargins.style.top = `${marginPx}px`;
      tplPreviewMargins.style.left = `${marginPx}px`;
      tplPreviewMargins.style.right = `${marginPx}px`;
      tplPreviewMargins.style.bottom = `${marginPx}px`;
    }

    const hasStage = availW > 0 && availH > 0;
    const needsScroll = hasStage && ((scale > (fitScale + 0.01)) || (scaledW > availW + 2) || (scaledH > availH + 2));
    tplPreviewStage.style.overflow = needsScroll ? 'auto' : 'hidden';

    if (tplPreviewLabel) {
      const label = selPageSize?.selectedOptions?.[0]?.textContent || spec.key;
      tplPreviewLabel.textContent = `${label} • ${Math.round(spec.wMm)}×${Math.round(spec.hMm)} mm • margini ${Math.round(spec.marginMm)} mm`;
    }
    if (tplPreviewScale) {
      const refScale = (scale * pagePxW) / a4PxW;
      tplPreviewScale.textContent = `Scala ${Math.round(scale * 100)}% (rif. A4: ${Math.round(refScale * 100)}%)`;
    }
  }

  let aiModal = null;
  let aiModalBackdrop = null;
  let btnAiClose = null;
  let btnAiSave = null;
  let btnAiTest = null;
  let aiEnabled = null;
  let aiProvider = null;
  let openaiKey = null;
  let openaiModel = null;
  let openaiKeyHint = null;
  let geminiKey = null;
  let geminiModel = null;
  let geminiKeyHint = null;
  let aiStatus = null;
  let aiUiBound = false;

  const authModal = el('authModal');
  const authModalBackdrop = el('authModalBackdrop');
  const btnAuthClose = el('btnAuthClose');
  const authModalTitle = el('authModalTitle');
  const authEmail = el('authEmail');
  const authPassword = el('authPassword');
  const authUsername = el('authUsername');
  const authOtpCode = el('authOtpCode');
  const btnAuthLogin = el('btnAuthLogin');
  const btnAuthRegister = el('btnAuthRegister');
  const authStatus = el('authStatus');

  function resolveAiUi() {
    aiModal = el('aiModal');
    aiModalBackdrop = el('aiModalBackdrop');
    btnAiClose = el('btnAiClose');
    btnAiSave = el('btnAiSave');
    btnAiTest = el('btnAiTest');
    aiEnabled = el('aiEnabled');
    aiProvider = el('aiProvider');
    openaiKey = el('openaiKey');
    openaiModel = el('openaiModel');
    openaiKeyHint = el('openaiKeyHint');
    geminiKey = el('geminiKey');
    geminiModel = el('geminiModel');
    geminiKeyHint = el('geminiKeyHint');
    aiStatus = el('aiStatus');
  }

  function bindAiUiOnce() {
    if (aiUiBound) return;
    resolveAiUi();
    if (!aiModal) return;
    if (btnAiClose) btnAiClose.addEventListener('click', hideAiModal);
    if (aiModalBackdrop) aiModalBackdrop.addEventListener('click', hideAiModal);
    if (btnAiSave) btnAiSave.addEventListener('click', saveAiSettings);
    if (btnAiTest) btnAiTest.addEventListener('click', testAiSettings);
    aiUiBound = true;
  }

  function showAiModal() {
    bindAiUiOnce();
    resolveAiUi();
    if (!aiModal) return;
    aiModal.classList.remove('hidden');
    aiModal.setAttribute('aria-hidden', 'false');
  }

  function hideAiModal() {
    resolveAiUi();
    if (!aiModal) return;
    aiModal.classList.add('hidden');
    aiModal.setAttribute('aria-hidden', 'true');
    if (aiStatus) aiStatus.textContent = '';
  }

  function setAiStatus(msg) {
    resolveAiUi();
    if (!aiStatus) return;
    aiStatus.textContent = String(msg || '');
  }

  function setSelectValue(selectEl, value) {
    if (!selectEl) return;
    const val = String(value || '').trim();
    if (!val) return;
    const exists = Array.from(selectEl.options).some((o) => o.value === val);
    if (!exists) {
      const opt = document.createElement('option');
      opt.value = val;
      opt.textContent = `${val} (custom)`;
      selectEl.appendChild(opt);
    }
    selectEl.value = val;
  }

  function setCategoryValue(selectEl, value) {
    if (!selectEl) return;
    const val = String(value || '').trim();
    if (!val) return;
    const exists = Array.from(selectEl.options).some((o) => o.value === val);
    if (!exists) {
      const opt = document.createElement('option');
      opt.value = val;
      opt.textContent = val;
      selectEl.appendChild(opt);
    }
    selectEl.value = val;
  }

  function formatKeyHint(info) {
    if (!info || !info.has_key) return 'Inserisci Chiave AI';
    const masked = String(info.api_key_masked || '').trim();
    const tail = masked.replace(/[^a-zA-Z0-9]/g, '').slice(-4);
    if (tail) return `Key ...${tail}`;
    return 'Key ok';
  }

  async function loadAiSettings() {
    if (!apiReady()) return null;
    try {
      const res = await window.pywebview.api.get_cloud_ai_settings();
      if (!res || !res.ok) {
        log(`Impostazioni AI non disponibili: ${res?.error || 'sconosciuto'}`);
        return null;
      }
      const s = res.settings || {};
      resolveAiUi();
      if (aiEnabled) aiEnabled.checked = !!s.enabled;
      if (aiProvider) aiProvider.value = String(s.provider || 'auto');
      setSelectValue(openaiModel, s?.openai?.model || '');
      setSelectValue(geminiModel, s?.gemini?.model || '');
      if (openaiKeyHint) openaiKeyHint.textContent = formatKeyHint(s?.openai);
      if (geminiKeyHint) geminiKeyHint.textContent = formatKeyHint(s?.gemini);
      return s;
    } catch (e) {
      log(`Errore lettura impostazioni AI: ${e}`);
      return null;
    }
  }

  async function saveAiSettings() {
    if (!apiReady()) return;
    resolveAiUi();
    const payload = {
      enabled: !!(aiEnabled && aiEnabled.checked),
      provider: aiProvider ? String(aiProvider.value || 'auto') : 'auto',
      openai: {
        api_key: openaiKey ? String(openaiKey.value || '').trim() : '',
        model: openaiModel ? String(openaiModel.value || '').trim() : '',
      },
      gemini: {
        api_key: geminiKey ? String(geminiKey.value || '').trim() : '',
        model: geminiModel ? String(geminiModel.value || '').trim() : '',
      },
    };
    try {
      const res = await window.pywebview.api.set_cloud_ai_settings(payload);
      if (!res || !res.ok) {
        setAiStatus(`Salvataggio fallito: ${res?.error || 'sconosciuto'}`);
        return;
      }
      if (openaiKey) openaiKey.value = '';
      if (geminiKey) geminiKey.value = '';
      setAiStatus('Salvato.');
      await loadAiSettings();
    } catch (e) {
      setAiStatus(`Errore salvataggio: ${e}`);
    }
  }

  async function testAiSettings() {
    if (!apiReady()) return;
    try {
      setAiStatus('Test in corso...');
      const res = await window.pywebview.api.test_cloud_ai();
      if (!res || !res.ok) {
        setAiStatus('Test Fallito');
        return;
      }
      setAiStatus(`OK. Provider: ${res.provider || 'n/d'}`);
    } catch (e) {
      setAiStatus(`Errore test: ${e}`);
    }
  }

  const fileList = el('fileList');
  const filesCount = el('filesCount');

  const progFill = el('progFill');
  const progText = el('progText');
  const progLabel = el('progLabel');
  const progSpinner = el('progSpinner');
  const progressState = { target: 0, display: 0, animId: null };

  const pillValue = el('pillValue');
  const pillSpinner = el('pillSpinner');
  const logEl = el('log');

  const prevTitle = el('prevTitle');
  const prevMeta = el('prevMeta');
  const prevDifficulty = el('prevDifficulty');
  const prevPrepTime = el('prevPrepTime');
  const prevCookTime = el('prevCookTime');
  const prevCategory = el('prevCategory');

  const previewTitleCanvas = document.createElement('canvas');
  const previewTitleCtx = previewTitleCanvas.getContext('2d');
  const PREVIEW_TITLE_FONT_MAX = 28;
  const PREVIEW_TITLE_FONT_MIN = 14;
  const PREVIEW_TITLE_PADDING = 12;

  const dietVegetarian = el('dietVegetarian');
  const dietVegan = el('dietVegan');
  const dietGlutenFree = el('dietGlutenFree');
  const dietLactoseFree = el('dietLactoseFree');
  const prevIngredients = el('prevIngredients');
  const prevSteps = el('prevSteps');

  const prevAllergens = el('prevAllergens');
  const prevEquipment = el('prevEquipment');
  const prevCostKcal = el('prevCostKcal');
  const prevWine = el('prevWine');
  const prevWineTemp = el('prevWineTemp');
  const prevWineRegion = el('prevWineRegion');
  const prevWineVintage = el('prevWineVintage');
  const prevWineVintageNote = el('prevWineVintageNote');
  const prevSeason = el('prevSeason');
  const missingPanel = el('missingPanel');
  const missingList = el('missingList');
  const missingEmpty = el('missingEmpty');
  const btnMissingCopy = el('btnMissingCopy');

  let archiveModal = null;
  let archiveModalBackdrop = null;
  let btnArchiveClose = null;
  let btnArchiveSearch = null;
  let btnArchiveDelete = null;
  let btnArchiveExport = null;
  let btnArchiveFiltersToggle = null;
  let archiveFiltersPanel = null;
  let archQuery = null;
  let archIngredient = null;
  let archCategory = null;
  let archDifficulty = null;
  let archServingsMin = null;
  let archServingsMax = null;
  let archSeasonality = null;
  let archPrepMin = null;
  let archPrepMax = null;
  let archCookMin = null;
  let archCookMax = null;
  let archTotalMin = null;
  let archTotalMax = null;
  let archKcal100Min = null;
  let archKcal100Max = null;
  let archKcalTotMin = null;
  let archKcalTotMax = null;
  let archCostMin = null;
  let archCostMax = null;
  let archProtein100Min = null;
  let archProtein100Max = null;
  let archFat100Min = null;
  let archFat100Max = null;
  let archFiber100Min = null;
  let archFiber100Max = null;
  let archCarb100Min = null;
  let archCarb100Max = null;
  let archSugar100Min = null;
  let archSugar100Max = null;
  let archProteinTotMin = null;
  let archProteinTotMax = null;
  let archFatTotMin = null;
  let archFatTotMax = null;
  let archFiberTotMin = null;
  let archFiberTotMax = null;
  let archCarbTotMin = null;
  let archCarbTotMax = null;
  let archSugarTotMin = null;
  let archSugarTotMax = null;
  let archSat100Min = null;
  let archSat100Max = null;
  let archMono100Min = null;
  let archMono100Max = null;
  let archPoly100Min = null;
  let archPoly100Max = null;
  let archChol100Min = null;
  let archChol100Max = null;
  let archSatTotMin = null;
  let archSatTotMax = null;
  let archMonoTotMin = null;
  let archMonoTotMax = null;
  let archPolyTotMin = null;
  let archPolyTotMax = null;
  let archCholTotMin = null;
  let archCholTotMax = null;
  let archSodium100Min = null;
  let archSodium100Max = null;
  let archSodiumTotMin = null;
  let archSodiumTotMax = null;
  let archCostTotalMin = null;
  let archCostTotalMax = null;
  let archDietVegetarian = null;
  let archDietVegan = null;
  let archDietGlutenFree = null;
  let archDietLactoseFree = null;
  let archMissingOnly = null;
  let archMissingField = null;
  let archExcludeAllergens = null;
  let archStatus = null;
  let archSelAll = null;
  let archTbody = null;
  let archiveUiBound = false;

  function resolveArchiveUi() {
    archiveModal = el('archiveModal');
    archiveModalBackdrop = el('archiveModalBackdrop');
    btnArchiveClose = el('btnArchiveClose');
    btnArchiveSearch = el('btnArchiveSearch');
    btnArchiveDelete = el('btnArchiveDelete');
    btnArchiveExport = el('btnArchiveExport');
    btnArchiveFiltersToggle = el('btnArchiveFiltersToggle');
    archiveFiltersPanel = el('archiveFiltersPanel');
    archQuery = el('archQuery');
    archIngredient = el('archIngredient');
    archCategory = el('archCategory');
    archDifficulty = el('archDifficulty');
    archServingsMin = el('archServingsMin');
    archServingsMax = el('archServingsMax');
    archSeasonality = el('archSeasonality');
    archPrepMin = el('archPrepMin');
    archPrepMax = el('archPrepMax');
    archCookMin = el('archCookMin');
    archCookMax = el('archCookMax');
    archTotalMin = el('archTotalMin');
    archTotalMax = el('archTotalMax');
    archKcal100Min = el('archKcal100Min');
    archKcal100Max = el('archKcal100Max');
    archKcalTotMin = el('archKcalTotMin');
    archKcalTotMax = el('archKcalTotMax');
    archCostMin = el('archCostMin');
    archCostMax = el('archCostMax');
    archProtein100Min = el('archProtein100Min');
    archProtein100Max = el('archProtein100Max');
    archFat100Min = el('archFat100Min');
    archFat100Max = el('archFat100Max');
    archFiber100Min = el('archFiber100Min');
    archFiber100Max = el('archFiber100Max');
    archCarb100Min = el('archCarb100Min');
    archCarb100Max = el('archCarb100Max');
    archSugar100Min = el('archSugar100Min');
    archSugar100Max = el('archSugar100Max');
    archProteinTotMin = el('archProteinTotMin');
    archProteinTotMax = el('archProteinTotMax');
    archFatTotMin = el('archFatTotMin');
    archFatTotMax = el('archFatTotMax');
    archFiberTotMin = el('archFiberTotMin');
    archFiberTotMax = el('archFiberTotMax');
    archCarbTotMin = el('archCarbTotMin');
    archCarbTotMax = el('archCarbTotMax');
    archSugarTotMin = el('archSugarTotMin');
    archSugarTotMax = el('archSugarTotMax');
    archSat100Min = el('archSat100Min');
    archSat100Max = el('archSat100Max');
    archMono100Min = el('archMono100Min');
    archMono100Max = el('archMono100Max');
    archPoly100Min = el('archPoly100Min');
    archPoly100Max = el('archPoly100Max');
    archChol100Min = el('archChol100Min');
    archChol100Max = el('archChol100Max');
    archSatTotMin = el('archSatTotMin');
    archSatTotMax = el('archSatTotMax');
    archMonoTotMin = el('archMonoTotMin');
    archMonoTotMax = el('archMonoTotMax');
    archPolyTotMin = el('archPolyTotMin');
    archPolyTotMax = el('archPolyTotMax');
    archCholTotMin = el('archCholTotMin');
    archCholTotMax = el('archCholTotMax');
    archSodium100Min = el('archSodium100Min');
    archSodium100Max = el('archSodium100Max');
    archSodiumTotMin = el('archSodiumTotMin');
    archSodiumTotMax = el('archSodiumTotMax');
    archCostTotalMin = el('archCostTotalMin');
    archCostTotalMax = el('archCostTotalMax');
    archDietVegetarian = el('archDietVegetarian');
    archDietVegan = el('archDietVegan');
    archDietGlutenFree = el('archDietGlutenFree');
    archDietLactoseFree = el('archDietLactoseFree');
    archMissingOnly = el('archMissingOnly');
    archMissingField = el('archMissingField');
    archExcludeAllergens = el('archExcludeAllergens');
    archStatus = el('archStatus');
    archSelAll = el('archSelAll');
    archTbody = el('archTbody');
  }

  const costDishPrice = el('costDishPrice');
  const costTotalAcquisto = el('costTotalAcquisto');
  const costTotalRicetta = el('costTotalRicetta');
  const costPerPorzione = el('costPerPorzione');

  const NUT_KEYS = [
    'energia',
    'carboidrati_totali',
    'di_cui_zuccheri',
    'grassi_totali',
    'di_cui_saturi',
    'monoinsaturi',
    'polinsaturi',
    'proteine_totali',
    'colesterolo_totale',
    'fibre',
    'sodio',
  ];

  const COST_COLS = [
    'ingrediente',
    'scarto',
    'peso_min_acquisto',
    'prezzo_kg_ud',
    'quantita_usata',
    'prezzo_alimento_acquisto',
    'prezzo_calcolato',
  ];

  function getById(id) { return document.getElementById(id); }

  function nutId(key, scope) { return `nut_${key}_${scope}`; }
  function costId(i, key) { return `p${i}_${key}`; }

  function readNum(id) {
    const n = parseFloat(String(getById(id)?.value ?? '').replace(',', '.'));
    return Number.isFinite(n) ? n : null;
  }
  function writeNum(id, val) {
    const elx = getById(id);
    if (!elx) return;
    if (val === null || val === undefined || val === '') elx.value = '';
    else elx.value = String(val);
  }
  function readText(id) {
    const elx = getById(id);
    if (!elx) return '';
    return String(elx.value ?? '').trim();
  }
  function writeText(id, val) {
    const elx = getById(id);
    if (!elx) return;
    elx.value = (val === null || val === undefined) ? '' : String(val);
  }

  function cleanTitle(val) {
    if (!val) return '';
    let s = String(val).trim();
    s = s.replace(/\bTitolo\s*:\s*/gi, '').trim();
    if (s.includes('|')) {
      const parts = s.split('|').map((p) => p.trim()).filter(Boolean);
      const uniq = [];
      parts.forEach((p) => {
        if (!uniq.some((u) => u.toLowerCase() === p.toLowerCase())) uniq.push(p);
      });
      if (uniq.length) s = uniq[0];
    }
    return s;
  }

  function parseMinutes(raw) {
    if (!raw) return null;
    const s = String(raw).trim().toLowerCase();
    if (!s) return null;
    let h = 0;
    let m = 0;
    const mh = s.match(/(\d+)\s*h/);
    if (mh) h = parseInt(mh[1], 10) || 0;
    const mm = s.match(/(\d+)\s*(min|m)\b/);
    if (mm) m = parseInt(mm[1], 10) || 0;
    if (h || m) return (h * 60) + m;
    const mn = s.match(/(\d+)/);
    return mn ? parseInt(mn[1], 10) : null;
  }

  function coerceMinutes(val) {
    if (val === null || val === undefined || val === '') return null;
    const n = Number(val);
    if (Number.isFinite(n)) return n;
    return parseMinutes(val);
  }

  function extractTime(label, raw) {
    if (!raw) return null;
    const re = new RegExp(`${label}\\s*[:\\-]?\\s*([0-9][^,;]*)`, 'i');
    const m = String(raw).match(re);
    return m ? parseMinutes(m[1]) : null;
  }

  const authState = {
    token: null,
    user: null,
    quota: null,
    registrationData: null,  // Memorizza email/password durante flusso registrazione 2FA
  };

  const state = {
    pickInFlight: false,
    selectedPaths: [],
    outDir: null,
    inputDir: null,
    batchOutDir: null,
    batchRunning: false,
    template: null,
    lastRecipe: null,
    lastExportPath: null,
    templatesMeta: {},
    analysisTimer: null,
    batchTimer: null,
    lastBatchEventKey: null,
    lastTimeoutKey: null,
    lastLogMsg: null,
  };

  // Detect if running as web app or desktop app
  const isWebApp = () => window.location.protocol === 'https:' || window.location.protocol === 'http:';
  const isDesktopApp = () => !!window.pywebview;

  function apiReady() {
    // If web app, REST API is always ready
    if (isWebApp()) return true;
    // If desktop app, check PyWebView
    if (isDesktopApp()) return window.pywebview && window.pywebview.api;
    return false;
  }

  async function api(name, payload = {}) {
    if (!apiReady()) throw new Error('API non disponibile. Riavvia l\'app o reinstalla WebView2');
    const merged = { ...(payload || {}) };
    if (authState.token && !merged.token) merged.token = authState.token;
    merged._csrf = csrfToken;

    // PRIORITÀ: Se web app (https/http), usa SEMPRE REST API
    if (isWebApp()) {
      // Use REST API for web app (Vercel, browser)
      const apiBase = (window.CooksyAPI && window.CooksyAPI.baseURL) || (() => {
        // Fallback: prova stessa origine, poi Railway
        const origin = window.location.origin;
        if (!origin.includes('localhost') && !origin.includes('127.0.0.1')) {
          return origin;
        }
        return 'https://cooksy-finaly.up.railway.app';
      })();
      const endpoint = `/api/${name}`;
      const response = await fetch(`${apiBase}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(merged),
      });
      if (!response.ok) {
        throw new Error(`API error ${response.status}: ${response.statusText}`);
      }
      const res = await response.json();
      if (res && res.error && /sessione/i.test(String(res.error))) {
        clearAuthState();
        updateAuthUi();
        log('Sessione scaduta, effettua di nuovo il login.');
        showToast('Sessione scaduta, effettua di nuovo il login.', 'error');
      }
      return res;
    }

    // Fallback: Try PyWebView (desktop app only)
    if (isDesktopApp() && window.pywebview && window.pywebview.api) {
      const fn = window.pywebview.api[name];
      if (typeof fn === 'function') {
        const res = await fn(merged);
        if (res && res.error && /sessione/i.test(String(res.error))) {
          clearAuthState();
          updateAuthUi();
          log('Sessione scaduta, effettua di nuovo il login.');
          showToast('Sessione scaduta, effettua di nuovo il login.', 'error');
        }
        return res;
      }
    }

    // Se arriviamo qui, nessun metodo funziona
    throw new Error(`API method '${name}' not available`);
    function now() {
      const d = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    }

    // Normalize number format: convert comma to dot for input[type="number"]
    function normalizeNumberValue(val) {
      if (typeof val === 'string') {
        return val.replace(',', '.');
      }
      return val;
    }

    // Set value on number input, handling locale differences
    function setNumberInputValue(el, val) {
      if (!el) return;
      if (el.type === 'number') {
        el.value = normalizeNumberValue(val);
      } else {
        el.value = val;
      }
    }

    function showToast(msg, type = 'info', timeoutMs = 3200) {
      if (!toastEl) return;
      toastEl.textContent = String(msg || '');
      toastEl.classList.remove('error', 'success');
      if (type === 'error') toastEl.classList.add('error');
      if (type === 'success') toastEl.classList.add('success');
      toastEl.classList.add('show');
      if (toastTimer) clearTimeout(toastTimer);
      toastTimer = setTimeout(() => {
        toastEl.classList.remove('show');
      }, timeoutMs);
    }

    const logState = {
      items: [],
      maxItems: 150,
    };

    function log(msg) {
      if (!logEl) return;
      const text = String(msg || '').trim();
      if (!text) return;
      if (state.lastLogMsg === text) return;
      state.lastLogMsg = text;

      const time = now();
      const item = { time, text };
      logState.items.push(item);

      if (logState.items.length > logState.maxItems) {
        logState.items.shift();
      }

      logEl.innerHTML = '';
      logState.items.forEach((logItem) => {
        const li = document.createElement('li');
        li.className = 'logItem';
        const timeSpan = document.createElement('span');
        timeSpan.className = 'logTime';
        timeSpan.textContent = logItem.time;
        const msgSpan = document.createElement('span');
        msgSpan.className = 'logMessage';
        msgSpan.textContent = logItem.text;
        li.appendChild(timeSpan);
        li.appendChild(msgSpan);
        logEl.appendChild(li);
      });

      if (logEl.parentNode) {
        logEl.scrollTop = logEl.scrollHeight;
      }
    }

    function loadStoredAuth() {
      try {
        const raw = localStorage.getItem('authSession');
        if (!raw) return;
        const parsed = JSON.parse(raw);
        authState.token = parsed?.token || null;
        authState.user = parsed?.user || null;
        authState.quota = parsed?.quota || null;
      } catch (_) {
        // ignore
      }
    }

    function persistAuth() {
      try {
        localStorage.setItem('authSession', JSON.stringify({
          token: authState.token,
          user: authState.user,
          quota: authState.quota,
        }));
      } catch (_) {
        // ignore
      }
    }

    function clearAuthState() {
      authState.token = null;
      authState.user = null;
      authState.quota = null;
      persistAuth();
    }

    function updateAuthUi() {
      const logged = !!authState.user;
      const label = logged ? (authState.user.username || authState.user.email || 'Utente') : 'Ospite';
      if (authUserLabel) authUserLabel.textContent = label;

      // Mostra/nascondi data scadenza abbonamento
      const authSubscriptionExpiry = el('authSubscriptionExpiry');
      if (authSubscriptionExpiry) {
        if (logged && authState.quota && authState.quota.subscription_expires_at) {
          authSubscriptionExpiry.style.display = '';
          const expiry = new Date(authState.quota.subscription_expires_at);
          const formatted = expiry.toLocaleDateString('it-IT');
          authSubscriptionExpiry.textContent = `Scadenza: ${formatted}`;
        } else {
          authSubscriptionExpiry.style.display = 'none';
        }
      }

      updateQuotaWidgets();
      if (btnLogout) btnLogout.style.display = logged ? 'inline-flex' : 'none';
      if (btnLogin) btnLogin.style.display = logged ? 'none' : 'inline-flex';
      if (btnRegister) btnRegister.style.display = logged ? 'none' : 'inline-flex';

      // Subscription button
      const btnSubscription = el('btnSubscription');
      if (btnSubscription) {
        btnSubscription.style.display = logged ? 'inline-flex' : 'none';
      }
    }

    function updateQuotaWidgets() {
      const logged = !!authState.user;
      const quota = authState.quota;
      if (authQuotaLabel) {
        if (logged && quota) {
          const used = quota.recipes_used ?? '-';
          const limit = quota.recipes_limit ?? '-';
          authQuotaLabel.textContent = `Quota: ${used}/${limit}`;
        } else {
          authQuotaLabel.textContent = 'Quota: -';
        }
      }

      const qUsed = el('quotaUsed');
      const qLimit = el('quotaLimit');
      const qFill = el('quotaFill');
      const qPct = el('quotaPercent');
      if (qUsed && qLimit && qFill && qPct) {
        const usedNum = Number(quota?.recipes_used ?? 0) || 0;
        const limitNum = Number(quota?.recipes_limit ?? 0) || 0;
        qUsed.textContent = logged ? usedNum : '-';
        qLimit.textContent = logged && limitNum ? limitNum : '-';
        const pct = limitNum > 0 ? Math.min(100, Math.round((usedNum / limitNum) * 100)) : 0;
        qFill.style.width = `${pct}%`;
        qPct.textContent = logged && limitNum ? `${pct}% utilizzato` : 'Quota non disponibile';
      }
    }

    function setAuthStatus(msg, type) {
      if (!authStatus) return;
      authStatus.textContent = msg || '';
      authStatus.classList.remove('error', 'success');
      if (type === 'error') authStatus.classList.add('error');
      if (type === 'success') authStatus.classList.add('success');
    }

    function showAuthModal(mode = 'login') {
      // Ricerca dinamica del modal (potrebbe non essere stato trovato all'init)
      let authModal = document.getElementById('authModal');
      if (!authModal) {
        authModal = el('authModal');
      }

      if (!authModal) return;

      const authModalTitle = el('authModalTitle');
      const authUsername = el('authUsername');
      const authEmail = el('authEmail');
      const authPassword = el('authPassword');
      const authOtpCode = el('authOtpCode');
      const btnAuthLogin = el('btnAuthLogin');
      const btnAuthRegister = el('btnAuthRegister');

      if (authModalTitle) authModalTitle.textContent = mode === 'register' ? 'Registrazione' : 'Accesso';
      authModal.dataset.mode = mode;
      setAuthStatus('', null);

      // Mostra/nascondi campo username
      const authUsernameField = el('authUsernameField');
      if (authUsernameField) {
        authUsernameField.style.display = mode === 'register' ? '' : 'none';
      }

      // Mostra solo il pulsante corrispondente alla modalità
      if (btnAuthLogin) {
        btnAuthLogin.style.display = mode === 'login' ? '' : 'none';
      }
      if (btnAuthRegister) {
        btnAuthRegister.style.display = mode === 'register' ? '' : 'none';
      }

      // Aggiorna il testo del link di switch
      const authSwitchText = el('authSwitchText');
      const authSwitchLink = el('authSwitchLink');
      if (authSwitchText && authSwitchLink) {
        if (mode === 'login') {
          authSwitchText.innerHTML = 'Non hai un account? <a href="#" id="authSwitchLink" style="color: var(--accent); text-decoration: underline;">Registrati</a>';
        } else {
          authSwitchText.innerHTML = 'Hai già un account? <a href="#" id="authSwitchLink" style="color: var(--accent); text-decoration: underline;">Accedi</a>';
        }

        // Re-attach event listener dopo innerHTML update
        const newSwitchLink = el('authSwitchLink');
        if (newSwitchLink) {
          newSwitchLink.addEventListener('click', (e) => {
            e.preventDefault();
            showAuthModal(mode === 'login' ? 'register' : 'login');
          });
        }
      }

      // Reset dei campi
      if (authEmail) authEmail.value = '';
      if (authPassword) authPassword.value = '';
      if (authUsername) authUsername.value = '';
      if (authOtpCode) authOtpCode.value = '';

      // Mostra step 1 (password)
      showAuthStep(1);

      authModal.classList.remove('hidden');
      authModal.setAttribute('aria-hidden', 'false');

      if (mode === 'register' && authUsername) authUsername.focus();
      else if (authEmail) authEmail.focus();

      if (mode === 'register' && authUsername) authUsername.focus();
      else if (authEmail) authEmail.focus();
    }

    function hideAuthModal() {
      // Re-resolve in caso gli elementi non fossero pronti al primo load
      const modal = authModal || el('authModal');
      if (!modal) return;
      modal.classList.add('hidden');
      modal.setAttribute('aria-hidden', 'true');
    }

    async function authMe() {
      if (!apiReady()) return null;
      try {
        const res = await api('auth_me', { token: authState.token || '' });
        if (res && res.ok) {
          authState.user = res.user || null;
          authState.quota = res.quota || null;
          persistAuth();
          updateAuthUi();
          if (typeof rebindSubscriptionListeners === 'function') {
            rebindSubscriptionListeners();
          }
          return res;
        }
        clearAuthState();
        updateAuthUi();
        setAuthStatus('Sessione scaduta, effettua login.', 'error');
        showToast('Sessione scaduta, effettua login.', 'error');
        return res;
      } catch (e) {
        clearAuthState();
        updateAuthUi();
        setAuthStatus('Sessione scaduta, effettua login.', 'error');
        showToast('Sessione scaduta, effettua login.', 'error');
        return null;
      }
    }

    async function authLogin() {
      if (!apiReady()) return;
      const email = authEmail ? String(authEmail.value || '').trim() : '';
      const password = authPassword ? String(authPassword.value || '') : '';
      if (!email || !password) {
        setAuthStatus('Email e password obbligatorie', 'error');
        return;
      }
      try {
        setAuthStatus('Accesso in corso...');
        const res = await api('auth_login', { email, password });
        if (!res || !res.ok) {
          setAuthStatus(res?.error || 'Accesso non riuscito', 'error');
          if (res?.error && /bloccato/i.test(String(res.error))) {
            showToast(res.error, 'error', 4000);
          }
          return;
        }
        authState.token = res.token || null;
        persistAuth();
        await authMe();
        setAuthStatus('Accesso riuscito', 'success');
        hideAuthModal();
      } catch (e) {
        setAuthStatus(`Errore: ${e.message || e}`, 'error');
      }
    }

    async function authRegister() {
      if (!apiReady()) return;
      const email = authEmail ? String(authEmail.value || '').trim() : '';
      const password = authPassword ? String(authPassword.value || '') : '';
      const username = authUsername ? String(authUsername.value || '').trim() : '';
      if (!email || !password) {
        setAuthStatus('Email e password obbligatorie', 'error');
        return;
      }
      try {
        setAuthStatus('Registrazione in corso...');
        const res = await api('auth_register', { email, password, username: username || undefined });
        if (!res || !res.ok) {
          setAuthStatus(res?.error || 'Registrazione non riuscita', 'error');
          return;
        }
        // Registrazione riuscita - mostra selezione 2FA
        authState.registrationData = {
          email,
          password,
          username,
          user_id: res.user_id
        };
        persistAuth();

        // Mostra selezione 2FA method
        const sel = el('auth2faMethodSel');
        if (sel) sel.classList.remove('hidden');
        setAuthStatus('Scegli il metodo 2FA (Email o SMS)', 'info');
      } catch (e) {
        setAuthStatus(`Errore: ${e.message || e}`, 'error');
      }
    }

    function startTwoFaProcess() {
      if (!apiReady() || !authState.registrationData) return;

      // Recupera il metodo scelto
      const radioButtons = document.querySelectorAll('input[name="twofa_method"]');
      let method = 'email';
      for (const radio of radioButtons) {
        if (radio.checked) {
          method = radio.value;
          break;
        }
      }

      authState.registrationData.twofa_method = method;
      persistAuth();

      // Nascondi selezione 2FA
      const sel = el('auth2faMethodSel');
      if (sel) sel.classList.add('hidden');

      // Richiedi OTP con il metodo scelto
      requestOtp(authState.registrationData.email, 'registration', method);
    }

    async function requestOtp(email, purpose = 'registration', method = 'email') {
      if (!apiReady()) return;
      try {
        setAuthStatus('Invio codice in corso...');
        const res = await api('otp_request', { email, purpose, method });
        if (!res || !res.ok) {
          setAuthStatus(res?.error || 'OTP non inviato', 'error');
          return;
        }
        // Mostra step OTP
        showAuthStep(2);
        updateOtpStepHeader(method);
        setAuthStatus(`Codice OTP inviato via ${method}`, 'success');
      } catch (e) {
        setAuthStatus(`Errore OTP: ${e.message || e}`, 'error');
      }
    }

    function updateOtpStepHeader(method) {
      const header = el('authStep2Header');
      if (!header) return;

      if (method === 'sms') {
        header.textContent = '📱 Verifica il tuo numero SMS';
      } else {
        header.textContent = '📧 Verifica il tuo email';
      }
    }

    async function verifyOtp() {
      if (!apiReady()) return;
      const email = authState.registrationData?.email || (authEmail?.value || '').trim();
      const otpCode = authOtpCode ? String(authOtpCode.value || '').trim() : '';
      const purpose = authState.registrationData ? 'registration' : 'login';

      if (!email || !otpCode) {
        setAuthStatus('Email e OTP richiesti', 'error');
        return;
      }

      try {
        setAuthStatus('Verifica OTP in corso...');
        const res = await api('otp_verify', { email, otp_code: otpCode, purpose });
        if (!res || !res.ok) {
          setAuthStatus(res?.error || 'OTP non valido', 'error');
          return;
        }

        if (authState.registrationData) {
          // Flusso registrazione - passa a passkey
          showAuthStep(3);
          setAuthStatus('OTP verificato. Registra una passkey.', 'success');
        } else {
          // Flusso login - esegui accesso
          setAuthStatus('OTP verificato. Accesso...', 'success');
          await authLogin();
        }
      } catch (e) {
        setAuthStatus(`Errore: ${e.message || e}`, 'error');
      }
    }

    function showAuthStep(stepNum) {
      // Nascondi tutti gli step
      const step1 = el('authStep1');
      const step2 = el('authStep2');
      const step3 = el('authStep3');

      if (step1) step1.classList.add('hidden');
      if (step2) step2.classList.add('hidden');
      if (step3) step3.classList.add('hidden');

      // Mostra lo step richiesto
      const steps = [null, step1, step2, step3];
      if (steps[stepNum]) steps[stepNum].classList.remove('hidden');
    }

    async function startPasskeyRegistration() {
      if (!apiReady()) return;
      try {
        if (!window.PublicKeyCredential) {
          setAuthStatus('Passkey non supportato su questo dispositivo', 'warning');
          showAuthStep(1);
          return;
        }

        setAuthStatus('Preparazione registrazione passkey...');
        const res = await api('passkey_start_registration', {});
        if (!res || !res.ok) {
          setAuthStatus(res?.error || 'Errore registrazione passkey', 'error');
          return;
        }

        const options = res.options;
        if (!options || !options.challenge) {
          setAuthStatus('Opzioni passkey non valide', 'error');
          return;
        }

        options.challenge = new Uint8Array(Buffer.from(options.challenge, 'base64'));
        options.user.id = new Uint8Array(Buffer.from(options.user.id, 'base64'));
        if (options.excludeCredentials) {
          options.excludeCredentials = options.excludeCredentials.map(c => ({
            ...c,
            id: new Uint8Array(Buffer.from(c.id, 'base64'))
          }));
        }

        setAuthStatus('Usa l\'impronta digitale o Face ID per registrare...');
        const credential = await navigator.credentials.create({ publicKey: options });

        if (!credential) {
          setAuthStatus('Registrazione passkey annullata', 'warning');
          return;
        }

        const attestationResponse = credential.response;
        const regRes = await api('passkey_finish_registration', {
          credential_id: Buffer.from(credential.id).toString('base64'),
          client_data: Buffer.from(attestationResponse.clientDataJSON).toString('base64'),
          attestation_object: Buffer.from(attestationResponse.attestationObject).toString('base64'),
          challenge: res.challenge
        });

        if (!regRes || !regRes.ok) {
          setAuthStatus(regRes?.error || 'Errore salvataggio passkey', 'error');
          return;
        }

        setAuthStatus('Passkey registrato con successo!', 'success');
        setTimeout(() => showAuthStep(1), 1500);
      } catch (e) {
        if (e.name === 'NotSupportedError') {
          setAuthStatus('Passkey non supportato su questo browser', 'error');
        } else if (e.name === 'NotAllowedError') {
          setAuthStatus('Operazione annullata', 'warning');
        } else {
          setAuthStatus(`Errore: ${e.message || e}`, 'error');
        }
      }
    }

    async function authPasskeyLogin() {
      if (!apiReady()) return;
      const email = authEmail ? String(authEmail.value || '').trim() : '';

      if (!email) {
        setAuthStatus('Email richiesta', 'error');
        return;
      }

      try {
        if (!window.PublicKeyCredential) {
          setAuthStatus('Passkey non supportato su questo dispositivo', 'warning');
          showAuthStep(1);
          return;
        }

        setAuthStatus('Accesso passkey in corso...');
        const res = await api('passkey_start_assertion', { email });
        if (!res || !res.ok) {
          setAuthStatus(res?.error || 'Passkey non trovato', 'error');
          return;
        }

        const options = res.options;
        if (!options || !options.challenge) {
          setAuthStatus('Opzioni passkey non valide', 'error');
          return;
        }

        options.challenge = new Uint8Array(Buffer.from(options.challenge, 'base64'));
        if (options.allowCredentials) {
          options.allowCredentials = options.allowCredentials.map(c => ({
            ...c,
            id: new Uint8Array(Buffer.from(c.id, 'base64'))
          }));
        }

        setAuthStatus('Usa l\'impronta digitale o Face ID per accedere...');
        const assertion = await navigator.credentials.get({ publicKey: options });

        if (!assertion) {
          setAuthStatus('Autenticazione passkey annullata', 'warning');
          return;
        }

        const assertionResponse = assertion.response;
        const loginRes = await api('passkey_finish_assertion', {
          email,
          credential_id: Buffer.from(assertion.id).toString('base64'),
          client_data: Buffer.from(assertionResponse.clientDataJSON).toString('base64'),
          authenticator_data: Buffer.from(assertionResponse.authenticatorData).toString('base64'),
          signature: Buffer.from(assertionResponse.signature).toString('base64'),
          challenge: res.challenge
        });

        if (!loginRes || !loginRes.ok) {
          setAuthStatus(loginRes?.error || 'Autenticazione passkey fallita', 'error');
          return;
        }

        if (loginRes.requires_otp) {
          authState.otp_session = loginRes.otp_session;
          authState.temp_token = loginRes.temp_token;
          showAuthStep('otp');
        } else {
          authState.token = loginRes.token;
          authState.user = loginRes.user;
          showAuthStep('dashboard');
          updateAuthUi();
        }
      } catch (e) {
        if (e.name === 'NotSupportedError') {
          setAuthStatus('Passkey non supportato su questo browser', 'error');
        } else if (e.name === 'NotAllowedError') {
          setAuthStatus('Operazione annullata', 'warning');
        } else if (e.name === 'InvalidStateError') {
          setAuthStatus('Passkey non registrato su questo dispositivo', 'error');
        } else {
          setAuthStatus(`Errore: ${e.message || e}`, 'error');
        }
      }
    }


    async function authLogout() {
      try {
        if (authState.token) {
          await api('auth_logout', { token: authState.token });
        }
      } catch (_) {
        // ignore
      }
      clearAuthState();
      updateAuthUi();
    }

    // ====== PASSKEY / WEBAUTHN ======
    const PASSKEY_ENABLED = true;
    const btnAuthPasskeyRegister = el('btnAuthPasskeyRegister');
    const btnAuthPasskeyLogin = el('btnAuthPasskeyLogin');

    async function authPasskeyRegister() {
      if (!apiReady() || !window.PublicKeyCredential) {
        setAuthStatus('WebAuthn non supportato in questo browser', 'error');
        return;
      }
      const email = authEmail ? String(authEmail.value || '').trim() : '';
      if (!email) {
        setAuthStatus('Email richiesta per registrare passkey', 'error');
        return;
      }
      try {
        setAuthStatus('Avvio registrazione passkey...');
        const userRes = await api('get_user_by_email', { email });
        if (!userRes || !userRes.ok || !userRes.user_id) {
          setAuthStatus('Utente non trovato. Crea prima l’account.', 'error');
          return;
        }
        const start = await api('passkey_start_registration', { email, user_id: userRes.user_id, username: authUsername ? authUsername.value : undefined });
        if (!start || !start.ok) {
          setAuthStatus(start?.error || 'Errore avvio registrazione', 'error');
          return;
        }
        const dec = (b64) => Uint8Array.from(atob(b64), c => c.charCodeAt(0));
        const challenge = dec(start.challenge);
        const userId = dec(start.user.id);
        const credential = await navigator.credentials.create({
          publicKey: {
            rp: { name: start.rpName || 'Cooksy', id: start.rpId || 'localhost' },
            user: {
              id: userId,
              name: start.user.name || email,
              displayName: start.user.displayName || email,
            },
            challenge,
            pubKeyCredParams: start.pubKeyCredParams || [
              { type: 'public-key', alg: -7 },
              { type: 'public-key', alg: -257 },
            ],
            authenticatorSelection: start.authenticatorSelection || { userVerification: 'preferred' },
            timeout: start.timeout || 60000,
            attestation: start.attestation || 'none',
          }
        });
        if (!credential) {
          setAuthStatus('Registrazione passkey annullata', 'error');
          return;
        }
        const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
        const credentialId = b64(credential.rawId);
        const attObj = b64(credential.response.attestationObject);
        const clientData = b64(credential.response.clientDataJSON);
        const transports = credential.response.getTransports ? credential.response.getTransports() : [];
        const finish = await api('passkey_finish_registration', {
          user_id: userRes.user_id,
          credential_id: credentialId,
          attestation_object: attObj,
          client_data_json: clientData,
          challenge: start.challenge,
          transports,
        });
        if (!finish || !finish.ok) {
          setAuthStatus(finish?.error || 'Errore completamento registrazione', 'error');
          return;
        }
        setAuthStatus('Passkey registrata! Ora puoi usarla per accedere.', 'success');
        showToast('Passkey registrata con successo', 'success');
      } catch (e) {
        setAuthStatus(`Errore passkey: ${e.message || e}`, 'error');
      }
    }

    async function authPasskeyLogin() {
      if (!PASSKEY_ENABLED) {
        passkeyDisabled();
        return;
      }
      if (!apiReady() || !window.PublicKeyCredential) {
        setAuthStatus('WebAuthn non supportato in questo browser', 'error');
        return;
      }
      const email = authEmail ? String(authEmail.value || '').trim() : '';
      if (!email) {
        setAuthStatus('Email richiesta per login passkey', 'error');
        return;
      }
      try {
        setAuthStatus('Ricerca utente...');
        const userRes = await api('get_user_by_email', { email });
        if (!userRes || !userRes.ok || !userRes.user_id) {
          setAuthStatus('Utente non trovato', 'error');
          return;
        }
        const userId = userRes.user_id;
        setAuthStatus('Avvio autenticazione passkey...');
        const start = await api('passkey_start_assertion', { user_id: userId });
        if (!start || !start.ok) {
          setAuthStatus(start?.error || 'Errore avvio autenticazione', 'error');
          return;
        }
        const challenge = Uint8Array.from(atob(start.challenge), c => c.charCodeAt(0));
        const allowCredentials = (start.allowCredentials || []).map(c => ({
          type: c.type || 'public-key',
          id: Uint8Array.from(atob(c.id), ch => ch.charCodeAt(0)),
        }));
        const assertion = await navigator.credentials.get({
          publicKey: {
            challenge,
            rpId: start.rpId || 'localhost',
            allowCredentials,
            userVerification: 'preferred',
            timeout: 60000,
          }
        });
        if (!assertion) {
          setAuthStatus('Autenticazione passkey annullata', 'error');
          return;
        }
        const credentialId = btoa(String.fromCharCode(...new Uint8Array(assertion.rawId)));
        const finish = await api('passkey_finish_assertion', {
          user_id: userId,
          credential_id: credentialId,
          sign_count: assertion.response.signature ? assertion.response.signature.byteLength : 0,
          challenge: start.challenge,
        });
        if (!finish || !finish.ok) {
          setAuthStatus(finish?.error || 'Errore completamento autenticazione', 'error');
          return;
        }
        authState.token = finish.token || null;
        persistAuth();
        await authMe();
        setAuthStatus('Accesso con passkey riuscito!', 'success');
        hideAuthModal();
        showToast('Accesso con passkey riuscito', 'success');
      } catch (e) {
        setAuthStatus(`Errore passkey: ${e.message || e}`, 'error');
      }
    }

    function updateMissingPanel(fields) {
      if (!missingPanel || !missingList || !missingEmpty) return;
      const items = Array.isArray(fields) ? fields.filter((x) => String(x || '').trim()) : [];
      missingList.innerHTML = '';
      if (!items.length) {
        missingPanel.style.display = 'none';
        missingPanel.classList.remove('has-missing');
        missingEmpty.style.display = 'block';
        missingList.style.display = 'none';
        if (btnMissingCopy) btnMissingCopy.disabled = true;
        return;
      }
      items.forEach((item) => {
        const li = document.createElement('li');
        li.textContent = String(item);
        missingList.appendChild(li);
      });
      missingPanel.style.display = 'block';
      missingPanel.classList.add('has-missing');
      missingEmpty.style.display = 'none';
      missingList.style.display = 'block';
      if (btnMissingCopy) btnMissingCopy.disabled = false;
    }

    if (btnMissingCopy) {
      btnMissingCopy.addEventListener('click', async () => {
        if (!missingList) return;
        const items = Array.from(missingList.querySelectorAll('li'))
          .map((x) => x.textContent.trim())
          .filter(Boolean);
        if (!items.length) return;
        const text = items.join('\n');
        try {
          if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(text);
            log('Elenco copiato.');
          }
        } catch (e) {
          log(`Impossibile copiare l'elenco: ${e}`);
        }
      });
    }

    function setStatus(msg, busy = false) {
      if (pillValue) pillValue.textContent = String(msg || '');
      if (pillSpinner) pillSpinner.style.display = busy ? 'inline-block' : 'none';
    }

    function animateProgress() {
      if (!progFill) {
        progressState.animId = null;
        return;
      }
      const delta = progressState.target - progressState.display;
      if (Math.abs(delta) < 0.1) {
        progressState.display = progressState.target;
        progFill.style.width = `${progressState.target}%`;
        progressState.animId = null;
        return;
      }
      const step = Math.sign(delta) * Math.max(0.4, Math.abs(delta) * 0.12);
      progressState.display += step;
      if ((delta > 0 && progressState.display > progressState.target) || (delta < 0 && progressState.display < progressState.target)) {
        progressState.display = progressState.target;
      }
      progFill.style.width = `${progressState.display.toFixed(1)}%`;
      progressState.animId = requestAnimationFrame(animateProgress);
    }

    function setProgressTarget(p) {
      progressState.target = p;
      if (!progressState.animId) {
        progressState.animId = requestAnimationFrame(animateProgress);
      }
    }

    const STAGE_LABELS = {
      idle: 'Pronto',
      start: 'Analisi in corso',
      analyze: 'Analisi in corso',
      parse: 'Analisi in corso',
      export: 'Esportazione PDF',
      batch: 'Batch in corso',
      ai: 'Integrazione AI',
      ai_complete: 'Integrazione AI',
      enrich: 'Arricchimento dati',
      done: 'Completato',
      error: 'Errore',
    };

    function updateProgress(pct, stage, msg) {
      const p = Math.max(0, Math.min(100, Number(pct) || 0));
      setProgressTarget(p);
      const stageKey = String(stage || '').toLowerCase();
      let label = STAGE_LABELS[stageKey] || (stageKey || 'In corso');
      const detail = msg ? String(msg) : '';
      const extra = (stageKey === 'idle' && detail) ? '' : detail;
      if (stageKey === 'idle' && detail) label = detail;
      const progressText = `${p}% - ${label}${extra ? ' - ' + extra : ''}`;
      if (progLabel) progLabel.textContent = progressText;
      else if (progText) progText.textContent = progressText;
      const busy = p < 100 && stageKey !== 'idle' && stageKey !== 'done';
      if (progSpinner) progSpinner.style.display = busy ? 'inline-block' : 'none';
      if (busy) setStatus(label || 'In corso', true);
      else setStatus('Pronto', false);
    }

    function setButtons() {
      const hasFiles = state.selectedPaths.length > 0;
      if (btnAnalyze) btnAnalyze.disabled = !hasFiles || state.pickInFlight;
      if (btnExport) btnExport.disabled = !state.lastRecipe;
      const singleFile = state.selectedPaths.length === 1;
      if (btnPrint) btnPrint.disabled = !(state.lastRecipe && singleFile);
      if (btnArchiveSave) btnArchiveSave.disabled = !state.lastRecipe;
      if (btnBatchStart) btnBatchStart.disabled = !state.inputDir || state.batchRunning;
      if (btnBatchOpenOut) btnBatchOpenOut.disabled = !state.batchOutDir;
    }

    function renderFileList(items) {
      if (!fileList) return;
      fileList.innerHTML = '';
      const list = Array.isArray(items) ? items : [];
      list.forEach((it) => {
        const name = it?.path ? String(it.path).split(/[\\/]/).pop() : String(it);
        const chip = document.createElement('div');
        chip.className = 'fileChip';
        const dot = document.createElement('span');
        dot.className = 'dot';
        const nameSpan = document.createElement('span');
        nameSpan.textContent = name; // XSS-safe
        chip.appendChild(dot);
        chip.appendChild(nameSpan);
        fileList.appendChild(chip);
      });
      if (filesCount) filesCount.textContent = String(list.length);
    }

    function buildIngredientsText(ingredients) {
      if (!Array.isArray(ingredients)) return '';
      const lines = [];
      ingredients.forEach((it) => {
        if (!it || typeof it !== 'object') return;
        const name = String(it.name || '').trim();
        if (!name) return;
        const qty = it.qty !== undefined && it.qty !== null ? String(it.qty).trim() : '';
        const unit = it.unit ? String(it.unit).trim() : '';
        const line = [qty, unit, name].filter(Boolean).join(' ').trim();
        if (line) lines.push(`- ${line}`);
      });
      return lines.join('\n');
    }

    function sanitizeIngredientsText(text) {
      const raw = String(text || '');
      if (!raw.trim()) return '';
      const lines = raw.split(/\r?\n/);
      const cleaned = [];
      lines.forEach((line) => {
        const trimmed = String(line || '').trim();
        if (!trimmed) return;
        const plain = trimmed.replace(/^[-*\d\.\)\s]+/, '').trim();
        if (!plain) return;
        const lower = plain.toLowerCase();
        if (
          lower.includes('prezzi aggiornati') ||
          lower.startsWith('prezzi aggiorna') ||
          lower.startsWith('prezzi aggiorn') ||
          lower.includes('prezzo del piatto') ||
          lower.includes('dati costo')
        ) {
          return;
        }
        if (/\b(prezzi|prezzo|spesa|costo)\b/.test(lower) && !/\d/.test(lower)) return;
        if (/^€+$/.test(plain) || lower === '€' || lower === 'eur') return;
        if (lower.startsWith('allergeni') || lower.startsWith('tracce') || lower.startsWith('adatto a') || lower.startsWith('diete')) {
          return;
        }
        if (lower.includes('allergeni') && !/\d/.test(lower)) return;
        if (lower.includes(',') && !/\d/.test(lower) && /(glutine|latte|uova|tracce)/.test(lower)) return;
        cleaned.push(trimmed);
      });
      return cleaned.join('\n');
    }

    function normalizeUnitText(value) {
      const s = String(value || '').trim();
      if (!s) return '';
      return s.replace(/\b(ud|u|unita|unità|unit)\b/gi, 'pz');
    }

    function formatCurrency(value) {
      const s = String(value || '').trim();
      if (!s) return '';
      if (/€|eur/i.test(s)) return s;
      if (/\d/.test(s)) return `${s} €`;
      return s;
    }

    function formatPriceUnit(value) {
      let s = String(value || '').trim();
      if (!s) return '';
      s = s.replace(/\?\//g, '€/');
      if (!/€|eur/i.test(s)) {
        s = s.replace(/\s*\/\s*(kg|l|pz)\b/i, ' €/$1');
      }
      if (!/€|eur/i.test(s) && /\d/.test(s)) s = `${s} €`;
      return s;
    }

    function resolveEquipmentText(recipe) {
      const base = String(
        recipe?.equipment_text || recipe?.attrezzature_text || recipe?.attrezzature_generiche || ''
      ).trim();
      if (base) return base;
      const simple = String(
        recipe?.attrezzature_semplici || recipe?.['attrezzature semplici'] || recipe?.attrezzature_generiche || ''
      ).trim();
      const pro = String(
        recipe?.attrezzature_professionali || recipe?.['attrezzature professionali'] || recipe?.attrezzature_specifiche || ''
      ).trim();
      const pastry = String(recipe?.attrezzature_pasticceria || recipe?.['attrezzature pasticceria'] || '').trim();
      const parts = [];
      if (simple) parts.push(`Semplici: ${simple}`);
      if (pro) parts.push(`Professionali: ${pro}`);
      if (pastry) parts.push(`Pasticceria: ${pastry}`);
      return parts.join('\n');
    }

    function buildStepsText(steps) {
      if (!Array.isArray(steps)) return '';
      return steps.map((st, idx) => {
        const txt = typeof st === 'string' ? st : (st?.text || '');
        return txt ? `${idx + 1}. ${String(txt).trim()}` : '';
      }).filter(Boolean).join('\n');
    }

    function readNutritionTable() {
      const out = { '100g': {}, 'totale': {} };
      NUT_KEYS.forEach((key) => {
        const v100 = readNum(nutId(key, '100g'));
        const vtot = readNum(nutId(key, 'totale'));
        if (v100 !== null) out['100g'][key] = v100;
        if (vtot !== null) out['totale'][key] = vtot;
      });
      return out;
    }

    function writeNutritionTable(table) {
      const t100 = table?.['100g'] || {};
      const ttot = table?.['totale'] || {};
      NUT_KEYS.forEach((key) => {
        writeNum(nutId(key, '100g'), t100[key]);
        writeNum(nutId(key, 'totale'), ttot[key]);
      });
    }

    function readCostLines() {
      const lines = [];
      for (let i = 1; i <= 10; i++) {
        const row = {};
        let hasAny = false;
        COST_COLS.forEach((col) => {
          const v = readText(costId(i, col));
          if (v) hasAny = true;
          row[col] = v;
        });
        if (hasAny) lines.push(row);
      }
      return lines;
    }

    function writeCostLines(lines) {
      for (let i = 1; i <= 10; i++) {
        const row = lines && lines[i - 1] ? lines[i - 1] : {};
        COST_COLS.forEach((col) => {
          writeText(costId(i, col), row[col] || '');
        });
      }
    }

    function normalizeCostLines(lines) {
      if (!Array.isArray(lines)) return [];
      return lines.map((row) => {
        if (!row || typeof row !== 'object') return null;
        const qty = row.quantita_usata || row.qty || '';
        const unit = normalizeUnitText(row.unit_raw || row.unit || '');
        const priceUnitRaw = row.prezzo_kg_ud || (row.price_unit && row.price_value ? `${row.price_value} ${row.price_unit}` : '');
        const priceUnit = formatPriceUnit(priceUnitRaw);
        const scartoRaw = row.scarto || row.scarto_pct || row.waste_pct || '';
        const scartoVal = String(scartoRaw || '').trim();
        const scarto = scartoVal;
        return {
          ingrediente: row.ingrediente || row.ingredient || row.ingredient_raw || row.name || '',
          scarto,
          peso_min_acquisto: normalizeUnitText(row.peso_min_acquisto || row.min_purchase || ''),
          prezzo_kg_ud: priceUnit || '',
          quantita_usata: normalizeUnitText(row.quantita_usata || (qty && unit ? `${qty} ${unit}` : qty) || ''),
          prezzo_alimento_acquisto: row.prezzo_alimento_acquisto || '',
          prezzo_calcolato: row.prezzo_calcolato || row.cost || '',
        };
      }).filter(Boolean);
    }

    function collectRecipeFromUI() {
      const base = state.lastRecipe || {};
      const recipe = { ...base };
      recipe.title = prevTitle ? cleanTitle(prevTitle.value) : recipe.title;
      recipe.servings = prevMeta ? prevMeta.value.trim() : recipe.servings;
      recipe.difficulty = prevDifficulty ? prevDifficulty.value : recipe.difficulty;
      recipe.prep_time_min = prevPrepTime ? prevPrepTime.value : recipe.prep_time_min;
      recipe.cook_time_min = prevCookTime ? prevCookTime.value : recipe.cook_time_min;
      recipe.category = prevCategory ? prevCategory.value : recipe.category;
      recipe.ingredients_text = prevIngredients ? prevIngredients.value : recipe.ingredients_text;
      recipe.steps_text = prevSteps ? prevSteps.value : recipe.steps_text;
      recipe.allergens_text = prevAllergens ? prevAllergens.textContent.trim() : recipe.allergens_text;
      recipe.equipment_text = prevEquipment ? prevEquipment.textContent.trim() : recipe.equipment_text;
      recipe.notes = prevCostKcal ? prevCostKcal.textContent.trim() : recipe.notes;
      recipe.wine_pairing = prevWine ? prevWine.textContent.trim() : recipe.wine_pairing;
      recipe.vino_temperatura_servizio = prevWineTemp ? prevWineTemp.value.trim() : recipe.vino_temperatura_servizio;
      recipe.vino_regione = prevWineRegion ? prevWineRegion.value.trim() : recipe.vino_regione;
      recipe.vino_annata = prevWineVintage ? prevWineVintage.value.trim() : recipe.vino_annata;
      recipe.vino_motivo_annata = prevWineVintageNote ? prevWineVintageNote.value.trim() : recipe.vino_motivo_annata;
      recipe.stagionalita = prevSeason ? prevSeason.textContent.trim() : recipe.stagionalita;
      recipe.diet_flags = {
        vegetarian: !!(dietVegetarian && dietVegetarian.checked),
        vegan: !!(dietVegan && dietVegan.checked),
        gluten_free: !!(dietGlutenFree && dietGlutenFree.checked),
        lactose_free: !!(dietLactoseFree && dietLactoseFree.checked),
      };
      recipe.nutrition_table = readNutritionTable();
      recipe.cost_lines = readCostLines();
      recipe.template = selTemplate ? selTemplate.value : recipe.template;
      recipe.page_size = selPageSize ? selPageSize.value : recipe.page_size;
      if (costDishPrice) recipe.selling_price_per_portion = costDishPrice.value;

      const tempoParts = [];
      if (recipe.prep_time_min) tempoParts.push(`Prep ${recipe.prep_time_min} min`);
      if (recipe.cook_time_min) tempoParts.push(`Cottura ${recipe.cook_time_min} min`);
      if (tempoParts.length) recipe.tempo_dettaglio = tempoParts.join(', ');

      return recipe;
    }

    function applyRecipe(recipe) {
      if (!recipe) return;
      state.lastRecipe = recipe;
      const title = cleanTitle(recipe.title || recipe.titolo || recipe.nome || '');
      const servings = recipe.servings ?? recipe.porzioni ?? recipe.portions ?? '';
      const difficulty = recipe.difficulty || recipe.difficolta || recipe['difficoltà'] || '';
      const tempoDett = recipe.tempo_dettaglio || recipe.tempo || '';
      const prepVal = coerceMinutes(recipe.prep_time_min ?? recipe.tempo_preparazione) ?? extractTime('(?:prep|preparazione)', tempoDett);
      const cookVal = coerceMinutes(recipe.cook_time_min ?? recipe.tempo_cottura) ?? extractTime('(?:cottura|cook)', tempoDett);

      if (prevTitle) prevTitle.value = String(title || '');
      adjustPreviewTitleSize();
      if (prevMeta) prevMeta.value = String(servings || '');
      if (prevDifficulty) prevDifficulty.value = String(difficulty || '');
      if (prevPrepTime) prevPrepTime.value = prepVal ?? '';
      if (prevCookTime) prevCookTime.value = cookVal ?? '';
      if (prevCategory) setCategoryValue(prevCategory, recipe.category || recipe.categoria || '');

      let ingText = recipe.ingredients_text;
      if (!ingText && Array.isArray(recipe.ingredients)) {
        ingText = buildIngredientsText(recipe.ingredients);
      }
      let stepsText = recipe.steps_text;
      if (!stepsText && Array.isArray(recipe.steps)) {
        stepsText = buildStepsText(recipe.steps);
      }
      const ingTextClean = sanitizeIngredientsText(ingText || '');
      if (prevIngredients) prevIngredients.value = ingTextClean;
      if (prevSteps) prevSteps.value = stepsText || '';

      if (prevAllergens) prevAllergens.textContent = String(recipe.allergens_text || recipe.allergeni_elenco || '');
      if (prevEquipment) prevEquipment.textContent = resolveEquipmentText(recipe);
      if (prevCostKcal) prevCostKcal.textContent = String(recipe.notes || recipe.costkcal_text || '');
      if (prevWine) prevWine.textContent = String(recipe.wine_pairing || recipe.vino_descrizione || recipe.wine || '');
      if (prevWineTemp) prevWineTemp.value = String(
        recipe.vino_temperatura_servizio || recipe['vino temperatura servizio'] || recipe.wine_temperature || ''
      );
      if (prevWineRegion) prevWineRegion.value = String(recipe.vino_regione || recipe['vino regione'] || '');
      if (prevWineVintage) prevWineVintage.value = String(recipe.vino_annata || recipe['vino annata'] || '');
      if (prevWineVintageNote) prevWineVintageNote.value = String(
        recipe.vino_motivo_annata || recipe['vino motivo annata'] || ''
      );
      if (prevSeason) prevSeason.textContent = String(recipe.stagionalita || recipe['stagionalità'] || recipe.seasonality || '');

      const df = recipe.diet_flags || {};
      if (dietVegetarian) dietVegetarian.checked = !!df.vegetarian;
      if (dietVegan) dietVegan.checked = !!df.vegan;
      if (dietGlutenFree) dietGlutenFree.checked = !!df.gluten_free;
      if (dietLactoseFree) dietLactoseFree.checked = !!df.lactose_free;

      if (recipe.nutrition_table) writeNutritionTable(recipe.nutrition_table);
      else writeNutritionTable({});

      if (recipe.cost_lines) writeCostLines(normalizeCostLines(recipe.cost_lines));
      else if (recipe.cost_summary?.items) writeCostLines(normalizeCostLines(recipe.cost_summary.items));
      else writeCostLines([]);

      if (costDishPrice) costDishPrice.value = recipe.selling_price_per_portion || '';
      if (costTotalAcquisto) {
        const val = recipe.spesa_totale_acquisto || recipe['spesa totale acquisto'] || '';
        costTotalAcquisto.textContent = formatCurrency(val) || '-';
      }
      if (costTotalRicetta) {
        const val = recipe.spesa_totale_ricetta || recipe['spesa totale ricetta'] || recipe.cost_summary?.total_cost || '';
        costTotalRicetta.textContent = formatCurrency(val) || '-';
      }
      if (costPerPorzione) {
        const val = recipe.spesa_per_porzione || recipe['spesa per porzione'] || recipe.cost_summary?.cost_per_portion || '';
        costPerPorzione.textContent = formatCurrency(val) || '-';
      }

      setButtons();
    }

    function buildExampleRecipe() {
      return {
        title: 'Pasta al pomodoro e basilico',
        servings: '4',
        difficulty: 'Facile',
        prep_time_min: 10,
        cook_time_min: 20,
        category: 'Primi',
        ingredients_text: [
          '- 320 g spaghetti',
          '- 400 g pomodori pelati',
          '- 2 spicchi di aglio',
          '- 4 cucchiai olio extravergine d’oliva',
          '- Sale fino',
          '- Basilico fresco',
        ].join('\n'),
        steps_text: [
          'Soffriggi l’aglio nell’olio senza bruciarlo.',
          'Unisci i pomodori e cuoci 12-15 minuti.',
          'Lessa la pasta al dente e scolala.',
          'Salta la pasta nel sugo e aggiungi basilico.',
        ].join('\n'),
        allergens_text: 'Glutine',
        equipment_text: 'Pentola, padella, mestolo, scolapasta',
        notes: 'Aggiungi un mestolo di acqua di cottura per legare il sugo.',
        wine_pairing: 'Chianti giovane',
        vino_temperatura_servizio: '14-16 °C',
        vino_regione: 'Toscana',
        vino_annata: '2023',
        vino_motivo_annata: 'Fresco e fruttato',
        stagionalita: 'Estate',
        diet_flags: {
          vegetarian: true,
          vegan: true,
          gluten_free: false,
          lactose_free: true,
        },
        nutrition_table: {
          '100g': {
            energia: 140,
            carboidrati_totali: 24,
            di_cui_zuccheri: 3,
            grassi_totali: 3,
            di_cui_saturi: 0.5,
            monoinsaturi: 1.6,
            polinsaturi: 0.6,
            proteine_totali: 4,
            colesterolo_totale: 0,
            fibre: 2,
            sodio: 200,
          },
          totale: {
            energia: 2100,
            carboidrati_totali: 360,
            di_cui_zuccheri: 45,
            grassi_totali: 45,
            di_cui_saturi: 7,
            monoinsaturi: 24,
            polinsaturi: 9,
            proteine_totali: 60,
            colesterolo_totale: 0,
            fibre: 30,
            sodio: 3000,
          },
        },
        cost_lines: [
          {
            ingrediente: 'Spaghetti',
            scarto: '0%',
            peso_min_acquisto: '1 kg',
            prezzo_kg_ud: '2,40',
            quantita_usata: '320 g',
            prezzo_alimento_acquisto: '2,40',
            prezzo_calcolato: '0,77',
          },
          {
            ingrediente: 'Pomodori pelati',
            scarto: '0%',
            peso_min_acquisto: '800 g',
            prezzo_kg_ud: '1,80',
            quantita_usata: '400 g',
            prezzo_alimento_acquisto: '1,80',
            prezzo_calcolato: '0,90',
          },
          {
            ingrediente: 'Olio extravergine',
            scarto: '0%',
            peso_min_acquisto: '1 l',
            prezzo_kg_ud: '8,50 €/l',
            quantita_usata: '40 ml',
            prezzo_alimento_acquisto: '8,50',
            prezzo_calcolato: '0,34',
          },
          {
            ingrediente: 'Aglio',
            scarto: '5%',
            peso_min_acquisto: '200 g',
            prezzo_kg_ud: '4,00',
            quantita_usata: '10 g',
            prezzo_alimento_acquisto: '4,00',
            prezzo_calcolato: '0,04',
          },
          {
            ingrediente: 'Basilico',
            scarto: '0%',
            peso_min_acquisto: '50 g',
            prezzo_kg_ud: '12,00',
            quantita_usata: '10 g',
            prezzo_alimento_acquisto: '12,00',
            prezzo_calcolato: '0,12',
          },
        ],
        spesa_totale_acquisto: '28,70',
        spesa_totale_ricetta: '2,17',
        spesa_per_porzione: '0,54',
        selling_price_per_portion: '8,50',
      };
    }

    function isUiRecipeEmpty() {
      const title = prevTitle?.value?.trim();
      const ingredients = prevIngredients?.value?.trim();
      const steps = prevSteps?.value?.trim();
      return !(title || ingredients || steps);
    }

    function showTplModal() {
      bindTplUiOnce();
      if (tplModal) {
        tplModal.classList.remove('hidden');
        tplModal.setAttribute('aria-hidden', 'false');
        if (tplFrame) {
          tplFrame.setAttribute('scrolling', 'no');
          tplFrame.style.overflow = 'hidden';
        }
        if (tplZoomLabel) tplZoomLabel.textContent = `${Math.round(tplZoom * 100)}%`;
        requestAnimationFrame(() => updateTplPreviewScale());
        setTimeout(updateTplPreviewScale, 80);
      }
    }

    function hideTplModal() {
      bindTplUiOnce();
      if (tplModal) {
        tplModal.classList.add('hidden');
        tplModal.setAttribute('aria-hidden', 'true');
      }
    }

    function showArchiveModal() {
      resolveArchiveUi();
      bindArchiveUiOnce();
      if (!archiveModal) return;
      archiveModal.classList.remove('hidden');
      archiveModal.setAttribute('aria-hidden', 'false');
    }

    function hideArchiveModal() {
      resolveArchiveUi();
      if (!archiveModal) return;
      archiveModal.classList.add('hidden');
      archiveModal.setAttribute('aria-hidden', 'true');
    }

    function renderArchiveRows(items) {
      resolveArchiveUi();
      if (!archTbody) return;
      const formatDateIt = (val) => {
        if (!val) return '';
        const s = String(val).trim();
        const m = s.match(/(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}):(\d{2}))?/);
        if (!m) return s;
        const datePart = `${m[3]}-${m[2]}-${m[1]}`;
        if (m[4] && m[5] && m[6]) return `${datePart} ${m[4]}:${m[5]}:${m[6]}`;
        return datePart;
      };
      const extractNum = (recipe, keys) => {
        for (const k of keys) {
          const v = recipe[k];
          if (v !== null && v !== undefined && v !== '') {
            const n = parseFloat(String(v).toString().replace(',', '.'));
            if (!isNaN(n)) return n;
          }
        }
        return null;
      };
      archTbody.innerHTML = '';
      const rows = Array.isArray(items) ? items : [];
      rows.forEach((it) => {
        const tr = document.createElement('tr');

        const td1 = document.createElement('td');
        const chk = document.createElement('input');
        chk.type = 'checkbox';
        chk.className = 'archSel';
        chk.setAttribute('data-id', String(it.id));
        td1.appendChild(chk);

        const td2 = document.createElement('td');
        td2.textContent = it.title || '';

        const td3 = document.createElement('td');
        td3.textContent = it.category || '';

        const td4 = document.createElement('td');
        const recipe = (typeof it.recipe === 'object' && it.recipe) || {};
        const difficulty = recipe.difficolta || recipe.difficulty || '';
        td4.textContent = difficulty;

        const td5 = document.createElement('td');
        const servings = extractNum(recipe, ['servings', 'porzioni', 'servings_count']);
        td5.textContent = servings !== null ? servings.toString() : '';

        const td6 = document.createElement('td');
        const prepMin = extractNum(recipe, ['tempo_preparazione_minuti', 'prep_time_minutes', 'prep_min']);
        td6.textContent = prepMin !== null ? `${prepMin}m` : '';

        const td7 = document.createElement('td');
        const kcalTot = extractNum(recipe, ['energia_totale', 'kcal_totale', 'energy_total', 'kcal_tot', 'spesa_totale_ricetta']);
        td7.textContent = kcalTot !== null ? kcalTot.toFixed(0) : '';

        const td8 = document.createElement('td');
        const costPortion = extractNum(recipe, ['spesa_per_porzione', 'costo_per_porzione', 'cost_per_portion']);
        td8.textContent = costPortion !== null ? `€${costPortion.toFixed(2)}` : '';

        const td9 = document.createElement('td');
        td9.textContent = formatDateIt(it.updated_at || '');

        const td10 = document.createElement('td');
        const btn = document.createElement('button');
        btn.className = 'archiveActionBtn';
        btn.setAttribute('data-open', String(it.id));
        btn.textContent = 'Apri';
        td10.appendChild(btn);

        tr.appendChild(td1);
        tr.appendChild(td2);
        tr.appendChild(td3);
        tr.appendChild(td4);
        tr.appendChild(td5);
        tr.appendChild(td6);
        tr.appendChild(td7);
        tr.appendChild(td8);
        tr.appendChild(td9);
        tr.appendChild(td10);
        archTbody.appendChild(tr);
      });
      if (archStatus) archStatus.textContent = `${rows.length} risultati`;
    }

    function getSelectedArchiveIds() {
      resolveArchiveUi();
      if (!archTbody) return [];
      return Array.from(archTbody.querySelectorAll('input.archSel:checked')).map((x) => x.getAttribute('data-id'));
    }

    function bindArchiveUiOnce() {
      if (archiveUiBound) return;
      resolveArchiveUi();
      if (!archiveModal) return;
      if (archiveModalBackdrop) archiveModalBackdrop.addEventListener('click', hideArchiveModal);
      if (btnArchiveClose) btnArchiveClose.addEventListener('click', hideArchiveModal);
      if (btnArchiveSearch) btnArchiveSearch.addEventListener('click', archiveSearch);
      if (btnArchiveDelete) btnArchiveDelete.addEventListener('click', archiveDeleteSelected);
      if (btnArchiveExport) btnArchiveExport.addEventListener('click', archiveExportSelected);
      if (btnArchiveFiltersToggle && archiveFiltersPanel) {
        btnArchiveFiltersToggle.addEventListener('click', () => {
          archiveFiltersPanel.classList.toggle('is-hidden');
        });
      }
      if (archSelAll) archSelAll.addEventListener('change', () => {
        const checked = archSelAll.checked;
        if (archTbody) {
          Array.from(archTbody.querySelectorAll('input.archSel')).forEach((cb) => { cb.checked = checked; });
        }
      });
      if (archTbody) {
        archTbody.addEventListener('click', async (ev) => {
          const btn = ev.target && ev.target.closest('button[data-open]');
          if (!btn) return;
          const rid = btn.getAttribute('data-open');
          if (!rid) return;
          const res = await window.pywebview.api.archive_load(rid);
          if (res && res.ok && res.recipe) {
            applyRecipe(res.recipe);
            hideArchiveModal();
          } else {
            log(`Errore apertura ricetta: ${res?.error || 'sconosciuto'}`);
          }
        });
      }
      archiveUiBound = true;
    }

    async function archiveSearch() {
      if (!apiReady()) return;
      resolveArchiveUi();
      const numOrNull = (val) => {
        if (val === null || val === undefined) return null;
        const n = parseFloat(String(val).trim().replace(',', '.'));
        return Number.isFinite(n) ? n : null;
      };
      const requireDiets = [];
      if (archDietVegetarian?.checked) requireDiets.push('vegetariana');
      if (archDietVegan?.checked) requireDiets.push('vegana');
      if (archDietGlutenFree?.checked) requireDiets.push('senza glutine');
      if (archDietLactoseFree?.checked) requireDiets.push('senza lattosio');

      const excludeAllergens = (archExcludeAllergens?.value || '')
        .split(',')
        .map((x) => x.trim())
        .filter(Boolean);

      const payload = {
        query: archQuery?.value || '',
        ingredient: archIngredient?.value || '',
        category: archCategory?.value || '',
        missing_only: !!archMissingOnly?.checked,
        missing_field: archMissingField?.value || '',
        require_diets: requireDiets,
        exclude_allergens: excludeAllergens,
        difficulty: archDifficulty?.value || '',
        seasonality: archSeasonality?.value || '',
        servings_min: numOrNull(archServingsMin?.value),
        servings_max: numOrNull(archServingsMax?.value),
        prep_min: numOrNull(archPrepMin?.value),
        prep_max: numOrNull(archPrepMax?.value),
        cook_min: numOrNull(archCookMin?.value),
        cook_max: numOrNull(archCookMax?.value),
        total_min: numOrNull(archTotalMin?.value),
        total_max: numOrNull(archTotalMax?.value),
        kcal_100_min: numOrNull(archKcal100Min?.value),
        kcal_100_max: numOrNull(archKcal100Max?.value),
        kcal_tot_min: numOrNull(archKcalTotMin?.value),
        kcal_tot_max: numOrNull(archKcalTotMax?.value),
        cost_min: numOrNull(archCostMin?.value),
        cost_max: numOrNull(archCostMax?.value),
        protein_100_min: numOrNull(archProtein100Min?.value),
        protein_100_max: numOrNull(archProtein100Max?.value),
        fat_100_min: numOrNull(archFat100Min?.value),
        fat_100_max: numOrNull(archFat100Max?.value),
        fiber_100_min: numOrNull(archFiber100Min?.value),
        fiber_100_max: numOrNull(archFiber100Max?.value),
        carb_100_min: numOrNull(archCarb100Min?.value),
        carb_100_max: numOrNull(archCarb100Max?.value),
        sugar_100_min: numOrNull(archSugar100Min?.value),
        sugar_100_max: numOrNull(archSugar100Max?.value),
        protein_tot_min: numOrNull(archProteinTotMin?.value),
        protein_tot_max: numOrNull(archProteinTotMax?.value),
        fat_tot_min: numOrNull(archFatTotMin?.value),
        fat_tot_max: numOrNull(archFatTotMax?.value),
        fiber_tot_min: numOrNull(archFiberTotMin?.value),
        fiber_tot_max: numOrNull(archFiberTotMax?.value),
        carb_tot_min: numOrNull(archCarbTotMin?.value),
        carb_tot_max: numOrNull(archCarbTotMax?.value),
        sugar_tot_min: numOrNull(archSugarTotMin?.value),
        sugar_tot_max: numOrNull(archSugarTotMax?.value),
        sat_100_min: numOrNull(archSat100Min?.value),
        sat_100_max: numOrNull(archSat100Max?.value),
        mono_100_min: numOrNull(archMono100Min?.value),
        mono_100_max: numOrNull(archMono100Max?.value),
        poly_100_min: numOrNull(archPoly100Min?.value),
        poly_100_max: numOrNull(archPoly100Max?.value),
        chol_100_min: numOrNull(archChol100Min?.value),
        chol_100_max: numOrNull(archChol100Max?.value),
        sat_tot_min: numOrNull(archSatTotMin?.value),
        sat_tot_max: numOrNull(archSatTotMax?.value),
        mono_tot_min: numOrNull(archMonoTotMin?.value),
        mono_tot_max: numOrNull(archMonoTotMax?.value),
        poly_tot_min: numOrNull(archPolyTotMin?.value),
        poly_tot_max: numOrNull(archPolyTotMax?.value),
        chol_tot_min: numOrNull(archCholTotMin?.value),
        chol_tot_max: numOrNull(archCholTotMax?.value),
        sodium_100_min: numOrNull(archSodium100Min?.value),
        sodium_100_max: numOrNull(archSodium100Max?.value),
        sodium_tot_min: numOrNull(archSodiumTotMin?.value),
        sodium_tot_max: numOrNull(archSodiumTotMax?.value),
        cost_total_min: numOrNull(archCostTotalMin?.value),
        cost_total_max: numOrNull(archCostTotalMax?.value),
      };

      const res = await window.pywebview.api.archive_search(payload);
      if (!res || !res.ok) {
        log(`Errore archivio: ${res?.error || 'sconosciuto'}`);
        return;
      }
      renderArchiveRows(res.items || []);
    }

    async function archiveDeleteSelected() {
      if (!apiReady()) return;
      const ids = getSelectedArchiveIds();
      if (!ids.length) {
        log('Nessuna ricetta selezionata.');
        return;
      }
      const res = await window.pywebview.api.archive_delete({ ids });
      if (!res || !res.ok) {
        log(`Errore eliminazione: ${res?.error || 'sconosciuto'}`);
        return;
      }
      await archiveSearch();
    }

    async function archiveExportSelected() {
      if (!apiReady()) return;
      const ids = getSelectedArchiveIds();
      if (!ids.length) {
        log('Nessuna ricetta selezionata.');
        return;
      }
      const payload = {
        ids,
        template: selTemplate ? selTemplate.value : undefined,
        out_dir: state.outDir,
      };
      const res = await window.pywebview.api.archive_export_batch(payload);
      if (!res || !res.ok) {
        log(`Errore export archivio: ${res?.error || 'sconosciuto'}`);
        return;
      }
      log(`Esportate ${res.count || 0} ricette in ${res.out_dir || ''}`);
    }

    async function previewTemplateHtml() {
      if (!apiReady()) return;
      bindTplUiOnce();
      tplAutoFit = false;
      tplZoom = 1;
      const recipe = isUiRecipeEmpty() ? buildExampleRecipe() : collectRecipeFromUI();
      const template = selTemplate ? selTemplate.value : '';
      if (!template) {
        const msg = 'Template non selezionato.';
        log(msg);
        if (tplFrame) {
          tplFrame.srcdoc = `<html><body style="font-family:sans-serif;padding:16px">${msg}</body></html>`;
          showTplModal();
        }
        return;
      }
      const res = await window.pywebview.api.render_template_preview({ recipe, template });
      if (!res || !res.ok) {
        const errMsg = `Errore anteprima template: ${res?.error || 'sconosciuto'}`;
        log(errMsg);
        if (tplFrame) {
          tplFrame.srcdoc = `<html><body style="font-family:sans-serif;padding:16px">${errMsg}</body></html>`;
          showTplModal();
        }
        return;
      }
      if (tplFrame) {
        const spec = resolvePageSpec(selPageSize ? selPageSize.value : 'A4');
        tplFrame.srcdoc = buildPreviewPageCss(spec) + (res.html || '');
        tplFrame.onload = () => {
          updateTplPreviewScale();
          try {
            const doc = tplFrame.contentDocument;
            if (doc) {
              doc.addEventListener('wheel', (ev) => {
                if (!tplPreviewStage) return;
                if (ev.ctrlKey) return;
                tplPreviewStage.scrollTop += ev.deltaY;
                tplPreviewStage.scrollLeft += ev.deltaX;
                ev.preventDefault();
              }, { passive: false });
            }
          } catch (_) {
            // ignore
          }
        };
      }
      showTplModal();
    }

    async function pickFiles() {
      if (!apiReady()) return;
      if (state.pickInFlight) return;
      state.pickInFlight = true;
      setButtons();
      try {
        const res = await window.pywebview.api.pick_images();
        if (res && res.ok) {
          state.selectedPaths = Array.isArray(res.paths) ? res.paths : [];
          renderFileList(res.items || state.selectedPaths.map((p) => ({ path: p })));
          log(`Selezionati ${state.selectedPaths.length} file.`);
        } else if (res?.error) {
          log(`Errore selezione file: ${res.error}`);
        }
      } finally {
        state.pickInFlight = false;
        setButtons();
      }
    }

    async function pickInputFolder() {
      if (!apiReady()) return;
      const res = await window.pywebview.api.choose_input_folder();
      if (res && res.ok && res.path) {
        state.inputDir = res.path;
        if (folderLabel) folderLabel.textContent = `Cartella: ${shortPath(res.path)}`;
        log(`Cartella batch: ${res.path}`);
        setButtons();
      }
    }

    async function chooseOutDir() {
      if (!apiReady()) return;
      const res = await window.pywebview.api.choose_output_folder();
      if (res && res.ok && res.path) {
        state.outDir = res.path;
        if (outDirLabel) outDirLabel.textContent = `Cartella: ${shortPath(res.path)}`;
        log(`Output: ${res.path}`);
      }
    }

    function shortPath(p) {
      const s = String(p || '').trim();
      if (!s) return '';
      const parts = s.split(/[\\/]+/).filter(Boolean);
      if (parts.length <= 4) return s;
      const head = parts.slice(0, 2).join('\\');
      const tail = parts.slice(-2).join('\\');
      return `${head}\\...\\${tail}`;
    }

    async function analyze() {
      if (!apiReady()) return;
      if (!state.selectedPaths.length) {
        log('Seleziona prima dei file.');
        return;
      }
      setStatus('Analisi', true);
      updateProgress(0, 'start', 'Avvio analisi');
      updateMissingPanel([]);
      const payload = { paths: state.selectedPaths, ocr_strategy: 'multi' };
      const res = await window.pywebview.api.analyze_start(payload);
      if (!res || !res.ok) {
        log(`Errore avvio analisi: ${res?.error || 'sconosciuto'}`);
        return;
      }
      if (state.analysisTimer) clearInterval(state.analysisTimer);
      state.analysisTimer = setInterval(async () => {
        const prog = await window.pywebview.api.get_progress();
        if (prog) updateProgress(prog.pct, prog.stage, prog.msg);
        const r = await window.pywebview.api.analyze_result();
        if (r && r.ready) {
          clearInterval(state.analysisTimer);
          state.analysisTimer = null;
          if (r.ok && r.result && r.result.recipe) {
            applyRecipe(r.result.recipe);
            log('Analisi completata.');
            if (r.result.recipe?.ai_completion?.provider) {
              log(`AI completamento: ${r.result.recipe.ai_completion.provider}`);
            } else if (r.result.recipe?.cloud_ai?.provider) {
              log(`Cloud AI: ${r.result.recipe.cloud_ai.provider}`);
            }
            if (r.result.recipe?.ai_completion_error) {
              log(`AI errore: ${r.result.recipe.ai_completion_error}`);
            }
            if (Array.isArray(r.result.missing_fields) && r.result.missing_fields.length) {
              log(`Campi ancora mancanti: ${r.result.missing_fields.join(', ')}`);
            }
            updateMissingPanel(r.result.missing_fields || []);
            updateProgress(100, 'done', 'Completato');
          } else {
            const errMsg = r?.result?.error || r?.error || 'sconosciuto';
            log(`Errore analisi: ${errMsg}`);
            if (Array.isArray(r?.result?.missing_fields) && r.result.missing_fields.length) {
              log(`Campi ancora mancanti: ${r.result.missing_fields.join(', ')}`);
            }
            updateMissingPanel(r?.result?.missing_fields || []);
          }
          setButtons();
        }
      }, 600);
    }

    async function exportPdf() {
      if (!apiReady()) return;
      const recipe = collectRecipeFromUI();
      log('Export PDF in corso...');
      setStatus('Esportazione', true);
      updateProgress(10, 'export', 'In corso');
      const payload = {
        recipe,
        template: selTemplate ? selTemplate.value : undefined,
        page_size: selPageSize ? selPageSize.value : undefined,
        out_dir: state.outDir,
      };
      const res = await window.pywebview.api.export_pdf(payload);
      if (!res || !res.ok) {
        log(`Errore export: ${res?.error || 'sconosciuto'}`);
        setStatus('Errore export', false);
        return;
      }
      state.lastExportPath = res.out_path || res.output_path;
      log(`PDF esportato: ${state.lastExportPath || ''}`);
      updateProgress(100, 'export', 'PDF creato');
      setStatus('PDF creato', false);
    }

    async function printPdf() {
      if (!apiReady()) return;
      if (!state.lastRecipe) return;
      if (state.selectedPaths.length !== 1) {
        log('Stampa disponibile solo con un singolo file analizzato.');
        return;
      }
      const recipe = collectRecipeFromUI();
      log('Stampa in corso...');
      setStatus('Stampa', true);
      updateProgress(10, 'export', 'Preparazione stampa');
      const payload = {
        recipe,
        template: selTemplate ? selTemplate.value : undefined,
        page_size: selPageSize ? selPageSize.value : undefined,
        out_dir: state.outDir,
        suggested_name: `Stampa_${recipe.title || 'ricetta'}`,
      };
      const res = await window.pywebview.api.export_pdf(payload);
      if (!res || !res.ok) {
        log(`Errore stampa: ${res?.error || 'sconosciuto'}`);
        setStatus('Errore stampa', false);
        return;
      }
      const outPath = res.out_path || res.output_path;
      if (outPath) {
        const printRes = await window.pywebview.api.print_file(outPath);
        if (!printRes || !printRes.ok) {
          await window.pywebview.api.open_file(outPath);
          log(`Stampa: aperto ${outPath}`);
        } else {
          log(`Stampa: inviata a stampante (${outPath})`);
        }
      }
      updateProgress(100, 'export', 'Pronto');
      setStatus('Pronto', false);
    }

    async function batchStart() {
      if (!apiReady()) return;
      if (!state.inputDir) {
        log('Seleziona una cartella batch.');
        return;
      }
      const chkSkipProcessed = el('chkSkipProcessed');
      const selSkipMethod = el('selSkipMethod');
      const payload = {
        input_dir: state.inputDir,
        out_dir: state.outDir,
        template: selTemplate ? selTemplate.value : undefined,
        page_size: selPageSize ? selPageSize.value : undefined,
        export_pdf: true,
        export_docx: true,
        recursive: true,
        skip_processed: !!(chkSkipProcessed && chkSkipProcessed.checked),
        skip_method: selSkipMethod ? selSkipMethod.value : 'hash',
      };
      const res = await window.pywebview.api.batch_start(payload);
      if (!res || !res.ok) {
        log(`Errore batch: ${res?.error || 'sconosciuto'}`);
        return;
      }
      state.batchRunning = true;
      state.lastTimeoutKey = null;
      setButtons();
      if (state.batchTimer) clearInterval(state.batchTimer);
      let pollInterval = 800;  // Intervallo iniziale
      const schedulePoll = async () => {
        const st = await window.pywebview.api.batch_status();
        if (!st) {
          if (state.batchRunning) setTimeout(schedulePoll, pollInterval);
          return;
        }
        const s = st.state || {};
        const done = s.done || 0;
        const total = s.total || 0;
        const skipped = s.skipped || 0;
        const pct = total > 0 ? Math.round((done / total) * 100) : 0;
        let statusMsg = `File ${done}/${total}`;
        if (skipped > 0) statusMsg += ` (saltati: ${skipped})`;
        updateProgress(pct, 'batch', statusMsg);

        // Polling adattivo: veloce quando lavora, lento quando idle
        const isActive = st.running && (s.current_path || s.current_file);
        pollInterval = isActive ? 500 : 1500;
        const curFile = s.current_path || s.current_file || '';
        if (batchCurrentFile) {
          batchCurrentFile.textContent = curFile ? `File corrente: ${shortPath(curFile)}` : 'File corrente: -';
        }
        if (curFile && curFile !== state.lastBatchFile) {
          state.lastBatchFile = curFile;
          state.lastTimeoutKey = null;
          log(`Batch: ${curFile}`);
        }
        if (s.timeout_pending && s.timeout_file) {
          const key = `${s.timeout_file}:${s.timeout_started_at || ''}`;
          if (key !== state.lastTimeoutKey) {
            state.lastTimeoutKey = key;
            const msg = `Il file "${s.timeout_file}" sta impiegando oltre 5 minuti. Vuoi proseguire?`;
            const ok = window.confirm(msg);
            if (!ok) {
              await window.pywebview.api.batch_timeout_decision({ action: 'stop' });
              log('Batch interrotto dall\'utente dopo timeout.');
            } else {
              const msg2 = `Vuoi continuare ad attendere questa ricetta?\nOK = continua questa ricetta\nAnnulla = passa alla prossima`;
              const ok2 = window.confirm(msg2);
              const action = ok2 ? 'continue' : 'skip';
              await window.pywebview.api.batch_timeout_decision({ action });
              if (!ok2) {
                log(`Ricetta saltata: ${s.timeout_file}`);
              }
            }
          }
        }
        if (s.last_event) {
          const msg = typeof s.last_event === 'string' ? s.last_event : (s.last_event.message || s.last_event.msg || '');
          const key = typeof s.last_event === 'string' ? s.last_event : JSON.stringify(s.last_event);
          if (key && key !== state.lastBatchEventKey) {
            state.lastBatchEventKey = key;
            if (msg) log(msg);
          }
        }
        if (!st.running) {
          state.batchTimer = null;
          state.batchRunning = false;
          state.batchOutDir = s.output_dir || null;
          if (state.batchOutDir) log(`Batch completato: ${state.batchOutDir}`);
          setButtons();
        } else {
          // Continua polling con intervallo adattivo
          state.batchTimer = setTimeout(schedulePoll, pollInterval);
        }
      };
      schedulePoll();  // Avvia polling
    }

    async function openBatchOut() {
      if (!apiReady() || !state.batchOutDir) return;
      await window.pywebview.api.open_folder(state.batchOutDir);
    }

    async function saveToArchive() {
      if (!apiReady()) return;
      const recipe = collectRecipeFromUI();
      const res = await window.pywebview.api.archive_save({ recipe });
      if (!res || !res.ok) {
        log(`Errore salvataggio archivio: ${res?.error || 'sconosciuto'}`);
        return;
      }
      log(`Ricetta salvata in archivio (id ${res.id}).`);
    }

    async function loadTemplates() {
      let res = null;
      let usedApi = false;
      let retries = 0;
      const maxRetries = 3;

      log('DEBUG: Avvio loadTemplates...');

      // Retry loop: attendi che l'API sia pronta
      while (retries < maxRetries && !res) {
        try {
          const pywebviewApi = (window.pywebview && window.pywebview.api) ? window.pywebview.api : null;
          log(`DEBUG: pywebviewApi=${pywebviewApi ? 'exists' : 'null'}`);
          if (pywebviewApi && typeof pywebviewApi.get_templates === 'function') {
            log('DEBUG: Usando PyWebView API');
            usedApi = true;
            res = await pywebviewApi.get_templates();
            log(`Template caricati: ${res ? (Array.isArray(res) ? res.length : res.templates?.length || 0) : 0}`);
            break;
          } else if (pywebviewApi && typeof pywebviewApi.list_templates === 'function') {
            log('DEBUG: Usando PyWebView list_templates');
            usedApi = true;
            res = await pywebviewApi.list_templates();
            log(`Template caricati (list_templates): ${res ? (Array.isArray(res) ? res.length : res.templates?.length || 0) : 0}`);
            break;
          } else if (!pywebviewApi) {
            // Fallback to REST API for web/Vercel
            log('DEBUG: Fallback a REST API...');
            try {
              res = await api('get_templates');
              log(`Template caricati (REST API): ${res ? (Array.isArray(res) ? res.length : res.templates?.length || 0) : 0}`);
              log(`DEBUG: Risposta REST: ${JSON.stringify(res).substring(0, 100)}`);
              break;
            } catch (restErr) {
              log(`Errore REST API template: ${restErr.message || restErr}`);
              retries++;
              if (retries < maxRetries) {
                log(`DEBUG: Retry ${retries}/${maxRetries} tra 500ms...`);
                await new Promise(resolve => setTimeout(resolve, 500));
              } else {
                log('API template non pronta; uso template di default');
              }
            }
          } else {
            retries++;
            if (retries < maxRetries) {
              log(`API template non pronta (tentativo ${retries}/${maxRetries}); riprovo tra 500ms...`);
              await new Promise(resolve => setTimeout(resolve, 500));
            } else {
              log('API template non pronta; uso template di default');
            }
          }
        } catch (e) {
          log(`Errore caricamento template (tentativo ${retries + 1}/${maxRetries}): ${e.message || e}`);
          retries++;
          if (retries < maxRetries) {
            await new Promise(resolve => setTimeout(resolve, 500));
          }
        }
      }

      let rawTemplates = [];
      let meta = [];
      if (Array.isArray(res)) {
        rawTemplates = res;
      } else if (res && Array.isArray(res.templates)) {
        rawTemplates = res.templates;
        if (Array.isArray(res.templates_meta)) meta = res.templates_meta;
      }

      state.templatesMeta = {};
      meta.forEach((m) => {
        if (m && m.name) {
          state.templatesMeta[m.name] = m;
          state.templatesMeta[`html:${m.name}`] = m;
        }
      });

      const clean = [];
      const seen = new Set();
      const stripHtml = (val) => String(val || '').replace(/^html:/i, '');
      const capitalizeLabel = (val) => {
        const s = String(val || '').trim();
        if (!s) return '';
        return s.charAt(0).toUpperCase() + s.slice(1);
      };
      rawTemplates.forEach((t) => {
        if (!t) return;
        let id = '';
        let label = '';
        if (typeof t === 'string' || typeof t === 'number') {
          id = String(t);
        } else if (typeof t === 'object') {
          id = String(t.id || t.name || t.value || '');
          label = String(t.label || t.name || t.id || '');
        }
        const rawId = id;
        if (!label && rawId && rawId.toLowerCase() === 'template_ricetta_ai') {
          label = 'Default';
        }
        if (!id) return;
        if (!/^html:/i.test(id)) id = `html:${id}`;
        if (seen.has(id)) return;
        seen.add(id);
        clean.push({ id, label: capitalizeLabel(label) });
      });

      if (!clean.length) {
        clean.push({ id: 'html:Template_Ricetta_AI', label: 'Default' });
      }

      const tplStatus = el('tplStatus');

      if (selTemplate) {
        selTemplate.innerHTML = '';
        clean.forEach((t) => {
          const opt = document.createElement('option');
          const metaLabelRaw = state.templatesMeta[t.id]?.label;
          const normId = stripHtml(t.id).toLowerCase();
          const metaLabel = normId === 'template_ricetta_ai' ? 'Default' : metaLabelRaw;
          opt.value = t.id;
          opt.textContent = capitalizeLabel(metaLabel || t.label || t.id); // XSS-safe
          selTemplate.appendChild(opt);
        });
        const prefer = clean.find((t) => stripHtml(t.id).toLowerCase() === 'template_ricetta_ai');
        selTemplate.value = prefer ? prefer.id : clean[0].id;
      } else if (tplStatus) {
        tplStatus.textContent = 'Template UI non trovata';
      }
      if (btnTplPreview) btnTplPreview.disabled = !clean.length;
    }

    function bindEvents() {
      // Initialize UI zoom controls
      initUiZoom();

      if (btnPick) btnPick.addEventListener('click', pickFiles);
      if (btnPickFolder) btnPickFolder.addEventListener('click', pickInputFolder);
      if (btnClear) btnClear.addEventListener('click', () => {
        state.selectedPaths = [];
        renderFileList([]);
        setButtons();
      });

      // Aggiungi listener per incollare testo ricetta
      const pasteRecipeText = el('pasteRecipeText');
      const btnPasteRecipe = el('btnPasteRecipe');
      if (btnPasteRecipe) {
        btnPasteRecipe.addEventListener('click', async () => {
          if (!pasteRecipeText || pasteRecipeText.value.trim() === '') {
            showToast('Incolla il testo della ricetta prima', 'error');
            return;
          }

          showToast('Elaborando testo ricetta...', 'info');
          try {
            const recipeText = pasteRecipeText.value;
            const result = await api('analyze_recipe_text', { text: recipeText });

            if (result && result.ok) {
              // Carica la ricetta elaborata
              if (result.recipe) {
                loadRecipe(result.recipe);
                showToast('Ricetta elaborata con successo!', 'success');
                pasteRecipeText.value = ''; // Pulisci l'area
              }
            } else {
              showToast(`Errore elaborazione: ${result?.error || 'sconosciuto'}`, 'error');
            }
          } catch (e) {
            showToast(`Errore: ${e.message || e}`, 'error');
          }
        });
      }

      if (btnAnalyze) btnAnalyze.addEventListener('click', analyze);
      if (btnExport) btnExport.addEventListener('click', exportPdf);
      if (btnPrint) btnPrint.addEventListener('click', printPdf);
      if (btnOutDir) btnOutDir.addEventListener('click', chooseOutDir);
      if (btnTplPreview) btnTplPreview.addEventListener('click', previewTemplateHtml);
      if (btnBatchStart) btnBatchStart.addEventListener('click', batchStart);
      if (btnBatchOpenOut) btnBatchOpenOut.addEventListener('click', openBatchOut);
      if (btnArchiveSave) btnArchiveSave.addEventListener('click', saveToArchive);
      if (btnArchiveOpen) btnArchiveOpen.addEventListener('click', () => {
        showArchiveModal();
        archiveSearch();
      });
      if (btnAiSettings) btnAiSettings.addEventListener('click', async () => {
        showAiModal();
        await loadAiSettings();
      });
      if (btnLogin) btnLogin.addEventListener('click', () => showAuthModal('login'));
      if (btnRegister) btnRegister.addEventListener('click', () => showAuthModal('register'));
      if (btnLogout) btnLogout.addEventListener('click', authLogout);
      if (btnAuthLogin) btnAuthLogin.addEventListener('click', (e) => {
        e.preventDefault();
        authLogin();
      });
      if (btnAuthRegister) btnAuthRegister.addEventListener('click', (e) => {
        e.preventDefault();
        authRegister();
      });
      if (btnAuthPasskeyLogin) btnAuthPasskeyLogin.addEventListener('click', (e) => {
        e.preventDefault();
        authPasskeyLogin();
      });

      // OTP buttons
      const btnOtpVerify = el('btnOtpVerify');
      const btnOtpCancel = el('btnOtpCancel');
      const btnPasskeyRegisterStart = el('btnPasskeyRegisterStart');
      const btnOtpCancelPasskey = el('btnOtpCancelPasskey');
      const auth2faMethodSel = el('auth2faMethodSel');

      // Listener per radio button di selezione 2FA method
      if (auth2faMethodSel) {
        const radioButtons = auth2faMethodSel.querySelectorAll('input[name="twofa_method"]');
        radioButtons.forEach(radio => {
          radio.addEventListener('change', () => {
            startTwoFaProcess();
          });
        });
      }

      if (btnOtpVerify) btnOtpVerify.addEventListener('click', (e) => {
        e.preventDefault();
        verifyOtp();
      });
      if (btnOtpCancel) btnOtpCancel.addEventListener('click', (e) => {
        e.preventDefault();
        authState.registrationData = null;
        persistAuth();
        showAuthStep(1);
        setAuthStatus('Registrazione annullata', 'info');
      });
      if (btnPasskeyRegisterStart) btnPasskeyRegisterStart.addEventListener('click', (e) => {
        e.preventDefault();
        startPasskeyRegistration();
      });
      if (btnOtpCancelPasskey) btnOtpCancelPasskey.addEventListener('click', (e) => {
        e.preventDefault();
        authState.registrationData = null;
        persistAuth();
        showAuthStep(1);
        setAuthStatus('Registrazione annullata', 'info');
      });

      if (btnAuthClose) btnAuthClose.addEventListener('click', hideAuthModal);
      if (authModalBackdrop) authModalBackdrop.addEventListener('click', hideAuthModal);
      if (prevTitle) prevTitle.addEventListener('input', adjustPreviewTitleSize);
      const chkSkipProcessed = el('chkSkipProcessed');
      const selSkipMethod = el('selSkipMethod');
      if (chkSkipProcessed && selSkipMethod) {
        const updateSkipMethodState = () => {
          selSkipMethod.disabled = !chkSkipProcessed.checked;
        };
        chkSkipProcessed.addEventListener('change', updateSkipMethodState);
        updateSkipMethodState();
      }
      if (selPageSize) selPageSize.addEventListener('change', () => {
        if (isTplModalVisible()) updateTplPreviewScale();
      });
      window.addEventListener('resize', () => {
        adjustPreviewTitleSize();
        if (isTplModalVisible()) updateTplPreviewScale();
      });
      bindTplUiOnce();
    }

    // Fallback: chiudi la modal auth anche se i listener non erano collegati al primo load
    document.addEventListener('click', (ev) => {
      const t = ev.target;
      if (!t || !(t instanceof HTMLElement)) return;
      const id = t.id;
      if (id === 'btnAuthClose' || id === 'authModalBackdrop') {
        hideAuthModal();
      }
      // Fallback per pulsanti auth modal
      if (id === 'btnAuthRegister') {
        ev.preventDefault();
        authRegister();
      }
      if (id === 'btnAuthLogin') {
        ev.preventDefault();
        authLogin();
      }
      if (id === 'btnAuthPasskeyLogin') {
        ev.preventDefault();
        authPasskeyLogin();
      }
      if (id === 'btnOtpVerify') {
        ev.preventDefault();
        verifyOtp();
      }
      if (id === 'btnPasskeyRegisterStart') {
        ev.preventDefault();
        startPasskeyRegistration();
      }
      // Fallback per pulsanti tier subscription
      if (id === 'btnTierFree' || id === 'btnTierPro' || id === 'btnTierBusiness') {
        if (typeof selectTier === 'function') {
          const tier = id.replace('btnTier', '').toLowerCase();
          selectTier(tier);
        }
      }
      // Fallback per pulsante abbonamento
      if (id === 'btnSubscription') {
        if (typeof showSubscriptionModal === 'function') {
          showSubscriptionModal();
        }
      }
    });

    // ============ TERMS & CONDITIONS ============
    // Funzione rimossa: caricamento Termini e Condizioni non più necessario.

    let initReady = false;
    async function continueInitialization() {
      if (!initReady) {
        initReady = true;
        loadStoredAuth();
        updateAuthUi();
        try {
          await loadTemplates();
        } catch (e) {
          log(`Init: loadTemplates fallita: ${e.message || e}`);
        }
        if (selPageSize) selPageSize.value = 'A4';
        if (apiReady()) {
          try {
            await authMe();
            const res = await window.pywebview.api.get_default_output_dir();
            if (res && res.ok && res.path) {
              state.outDir = res.path;
              if (outDirLabel) outDirLabel.textContent = `Cartella: ${shortPath(res.path)}`;
            }
          } catch (_) {
            // ignore
          }
        }
        if (outDirLabel && !state.outDir) {
          outDirLabel.textContent = 'Cartella: C:\\Users\\utente\\Desktop\\Elaborate';
        }
        // Mostra sempre una ricetta di esempio all'avvio; verrà sostituita al primo file analizzato
        if (!state.lastRecipe) {
          applyRecipe(buildExampleRecipe());
        }
        adjustPreviewTitleSize();
        setButtons();
        updateProgress(0, 'idle', 'Pronto');
      }
    }

    async function init() {
      // Termini e Condizioni rimossi: inizializza direttamente
      await continueInitialization();
    }

    // ====== MODAL CARICA E SCALA RICETTA ======
    const scaleModal = el('recipeScaleModal');
    const scaleBackdrop = el('recipeScaleBackdrop');
    const btnRecipeScale = el('btnRecipeScale');
    const btnScaleClose = el('btnScaleClose');
    const scaleRecipeId = el('scaleRecipeId');
    const btnScaleLoadRecipe = el('btnScaleLoadRecipe');
    const scaleLoadStatus = el('scaleLoadStatus');
    const scaleRecipeInfo = el('scaleRecipeInfo');
    const scaleOptions = el('scaleOptions');
    const scaleResults = el('scaleResults');
    const scaleRecipeTitle = el('scaleRecipeTitle');
    const scaleOriginalServings = el('scaleOriginalServings');
    const scaleIngredientsCount = el('scaleIngredientsCount');
    const scaleTargetServings = el('scaleTargetServings');
    const scaleFactorValue = el('scaleFactorValue');
    const scaleTargetWeight = el('scaleTargetWeight');
    const btnScaleApply = el('btnScaleApply');
    const scaleResultsTable = el('scaleResultsTable');
    const btnScaleCopyText = el('btnScaleCopyText');
    const btnScaleExport = el('btnScaleExport');
    const btnScaleSaveArchive = el('btnScaleSaveArchive');

    let currentLoadedRecipe = null;

    function showScaleModal() {
      if (scaleModal) {
        scaleModal.classList.remove('hidden');
        scaleRecipeId.focus();
      }
    }

    function hideScaleModal() {
      if (scaleModal) scaleModal.classList.add('hidden');
    }

    function showScaleStatus(msg, isError = false) {
      if (scaleLoadStatus) {
        scaleLoadStatus.textContent = msg;
        scaleLoadStatus.style.display = 'block';
        scaleLoadStatus.style.color = isError ? '#d32f2f' : '#2e7d32';
      }
    }

    async function loadRecipeFromArchive() {
      const recipeId = parseInt(scaleRecipeId.value || 0);
      if (recipeId <= 0) {
        showScaleStatus('ID ricetta non valido', true);
        return;
      }

      try {
        showScaleStatus('Caricamento in corso...');
        const response = await api('recipe_load', { id: recipeId });

        if (!response.ok) {
          showScaleStatus(`Errore: ${response.error}`, true);
          return;
        }

        currentLoadedRecipe = response.recipe;

        // Mostra info ricetta
        const title = currentLoadedRecipe.title || 'Senza titolo';
        const servings = currentLoadedRecipe.servings || 1;
        const ingredients = currentLoadedRecipe.ingredients || [];

        scaleRecipeTitle.textContent = title;
        scaleOriginalServings.textContent = servings;
        scaleIngredientsCount.textContent = ingredients.length;

        scaleRecipeInfo.style.display = 'block';
        scaleOptions.style.display = 'block';
        scaleResults.style.display = 'none';

        showScaleStatus(`Ricetta caricata: "${title}"`);
        scaleTargetServings.value = servings;
        scaleTargetWeight.value = 1000;
      } catch (err) {
        showScaleStatus(`Errore: ${err.message}`, true);
      }
    }

    async function scaleRecipe() {
      if (!currentLoadedRecipe) {
        showScaleStatus('Nessuna ricetta caricata', true);
        return;
      }

      const scaleType = document.querySelector('input[name="scaleType"]:checked')?.value || 'porzioni';
      const payload = { recipe: currentLoadedRecipe, scale_type: scaleType };

      if (scaleType === 'porzioni') {
        payload.target_servings = parseFloat(scaleTargetServings.value || 1);
      } else if (scaleType === 'fattore') {
        payload.factor = parseFloat(scaleFactorValue.value || 1);
      } else if (scaleType === 'peso') {
        payload.target_weight = parseFloat(scaleTargetWeight.value || 1000);
      }

      try {
        showScaleStatus('Scaling in corso...');
        const response = await api('recipe_scale', payload);

        if (!response.ok) {
          showScaleStatus(`Errore: ${response.error}`, true);
          return;
        }

        currentLoadedRecipe = response.recipe;
        displayScaledRecipe(response.recipe);
        showScaleStatus(`Ricetta scalata con fattore ${response.recipe.scale_factor}x`);
      } catch (err) {
        showScaleStatus(`Errore: ${err.message}`, true);
      }
    }

    function displayScaledRecipe(recipe) {
      const ingredients = recipe.ingredients || [];
      const factor = recipe.scale_factor || 1;

      const escapeHtml = (str) => String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');

      let html = '<table class="dataTable"><tr><th>Ingrediente</th><th>Quantità</th></tr>';

      ingredients.forEach(ing => {
        const name = escapeHtml(ing.name || ing.ingrediente || 'N/A');
        const qty = escapeHtml(ing.quantity || 0);
        const unit = escapeHtml(ing.unit || '');
        html += `<tr><td>${name}</td><td>${qty} ${unit}</td></tr>`;
      });

      html += '</table>';
      scaleResultsTable.innerHTML = html;
      scaleResults.style.display = 'block';
    }

    function copyScaledToClipboard() {
      if (!currentLoadedRecipe) return;

      const ingredients = currentLoadedRecipe.ingredients || [];
      let text = `${currentLoadedRecipe.title}\n`;
      text += `Porzioni: ${currentLoadedRecipe.scaled_servings}\n\n`;
      text += 'Ingredienti:\n';

      ingredients.forEach(ing => {
        const name = ing.name || ing.ingrediente || '';
        const qty = ing.quantity || 0;
        const unit = ing.unit || '';
        text += `- ${qty} ${unit} ${name}\n`;
      });

      navigator.clipboard.writeText(text);
      showScaleStatus('Copiato negli appunti');
    }

    async function exportScaledRecipe() {
      if (!currentLoadedRecipe) {
        showScaleStatus('Nessuna ricetta scalata', true);
        return;
      }
      showScaleStatus('Esportazione PDF...');
      try {
        const payload = {
          recipe: currentLoadedRecipe,
          template: selTemplate ? selTemplate.value : undefined,
          page_size: selPageSize ? selPageSize.value : undefined,
          out_dir: state.outDir,
        };
        const res = await api('export_pdf', payload);
        if (res && res.ok) {
          showScaleStatus('PDF esportato', false);
        } else {
          showScaleStatus(`Errore export: ${res?.error || 'sconosciuto'}`, true);
        }
      } catch (e) {
        showScaleStatus(`Errore export: ${e.message || e}`, true);
      }
    }

    async function saveScaledToArchive() {
      if (!currentLoadedRecipe) {
        showScaleStatus('Nessuna ricetta scalata', true);
        return;
      }
      showScaleStatus('Salvataggio in archivio...');
      try {
        const res = await api('archive_save', { recipe: currentLoadedRecipe });
        if (res && res.ok) {
          showScaleStatus(`Salvata in archivio (id ${res.id})`);
        } else {
          showScaleStatus(`Errore salvataggio: ${res?.error || 'sconosciuto'}`, true);
        }
      } catch (e) {
        showScaleStatus(`Errore salvataggio: ${e.message || e}`, true);
      }
    }

    // Event listeners Scale
    if (btnRecipeScale) btnRecipeScale.addEventListener('click', showScaleModal);
    if (btnScaleClose) btnScaleClose.addEventListener('click', hideScaleModal);
    if (scaleBackdrop) scaleBackdrop.addEventListener('click', hideScaleModal);
    if (btnScaleLoadRecipe) btnScaleLoadRecipe.addEventListener('click', loadRecipeFromArchive);

    // Toggle scale type options
    document.querySelectorAll('input[name="scaleType"]').forEach(radio => {
      radio.addEventListener('change', (e) => {
        el('scalePortionOpt').style.display = e.target.value === 'porzioni' ? 'block' : 'none';
        el('scaleFactorOpt').style.display = e.target.value === 'fattore' ? 'block' : 'none';
        el('scaleWeightOpt').style.display = e.target.value === 'peso' ? 'block' : 'none';
      });
    });

    // Buttons scale actions - tutti e tre gli elementi btnScaleApply
    const scaleApplyButtons = document.querySelectorAll('#btnScaleApply');
    scaleApplyButtons.forEach(btn => {
      btn.addEventListener('click', scaleRecipe);
    });

    if (btnScaleCopyText) btnScaleCopyText.addEventListener('click', copyScaledToClipboard);
    if (btnScaleExport) btnScaleExport.addEventListener('click', exportScaledRecipe);
    if (btnScaleSaveArchive) btnScaleSaveArchive.addEventListener('click', saveScaledToArchive);

    let initStarted = false;

    function initWhenReady() {
      if (initStarted) return;  // evita doppi avvii
      initStarted = true;
      const pv = el('pillValue');
      if (pv) pv.textContent = 'JS in esecuzione';
      init();
    }

    // Avvia bind degli eventi subito (non dipende da API), ma l'inizializzazione completa aspetta pywebview/DOM.
    bindEvents();

    // === Gestione tabella ingredienti dinamica ===
    let ingredientRowCount = 10; // Inizia con 10 righe

    function updateEmptyRowsVisibility() {
      const table = el('tblCost');
      if (!table) return;

      const rows = table.querySelectorAll('tbody tr');
      rows.forEach((row) => {
        const inputs = row.querySelectorAll('input');
        const hasContent = Array.from(inputs).some(input => input.value.trim() !== '');

        if (!hasContent) {
          row.classList.add('empty-row');
        } else {
          row.classList.remove('empty-row');
        }
      });
    }

    function addIngredientRow() {
      const table = el('tblCost');
      if (!table) return;

      const tbody = table.querySelector('tbody');
      ingredientRowCount++;
      const rowNum = ingredientRowCount;

      const newRow = document.createElement('tr');
      newRow.innerHTML = `
      <td><input class="dtInput" id="p${rowNum}_ingrediente" type="text" spellcheck="false" /></td>
      <td><input class="dtInput" id="p${rowNum}_scarto" type="text" spellcheck="false" /></td>
      <td><input class="dtInput" id="p${rowNum}_peso_min_acquisto" type="text" spellcheck="false" /></td>
      <td><input class="dtInput" id="p${rowNum}_prezzo_kg_ud" type="text" spellcheck="false" /></td>
      <td><input class="dtInput" id="p${rowNum}_quantita_usata" type="text" spellcheck="false" /></td>
      <td><div class="price-input-wrapper"><input class="dtInput" id="p${rowNum}_prezzo_alimento_acquisto" type="text" spellcheck="false" /><span class="currency-symbol">€</span></div></td>
      <td><div class="price-input-wrapper"><input class="dtInput" id="p${rowNum}_prezzo_calcolato" type="text" spellcheck="false" /><span class="currency-symbol">€</span></div></td>
    `;

      tbody.appendChild(newRow);

      // Aggiungi listeners alla nuova riga
      const ingredienteInput = el(`p${rowNum}_ingrediente`);
      if (ingredienteInput) {
        ingredienteInput.addEventListener('input', (e) => {
          updateEmptyRowsVisibility();
          updateIngredienteWidth(e.target);
        });
        ingredienteInput.addEventListener('blur', updateEmptyRowsVisibility);
        // Imposta larghezza iniziale
        updateIngredienteWidth(ingredienteInput);
      }

      // Focus sul nuovo campo ingrediente
      ingredienteInput?.focus();
    }

    // Aggiorna larghezza colonna ingrediente in base al testo
    function updateIngredienteWidth(input) {
      if (!input) return;

      // Calcola larghezza in base al contenuto
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      const style = window.getComputedStyle(input);
      ctx.font = `${style.fontSize} ${style.fontFamily}`;
      const textWidth = ctx.measureText(input.value || input.placeholder || 'Ingrediente').width;

      // Imposta larghezza con padding buffer
      const newWidth = Math.max(120, textWidth + 20);
      input.style.width = newWidth + 'px';
    }

    // Aggiungi listener su tutti gli input ingrediente
    function attachIngredientListeners() {
      const table = el('tblCost');
      if (!table) return;

      const rows = table.querySelectorAll('tbody tr');
      rows.forEach((row) => {
        const ingredienteInput = row.querySelector('input[id$="_ingrediente"]');
        if (ingredienteInput) {
          ingredienteInput.addEventListener('input', (e) => {
            updateEmptyRowsVisibility();
            updateIngredienteWidth(e.target);
          });
          ingredienteInput.addEventListener('blur', updateEmptyRowsVisibility);
          // Imposta larghezza iniziale
          updateIngredienteWidth(ingredienteInput);
        }
      });

      // Aggiorna visibilità iniziale
      updateEmptyRowsVisibility();
    }

    // Esegui dopo che il DOM è pronto
    document.addEventListener('DOMContentLoaded', () => {
      attachIngredientListeners();

      // Aggiungi listener al pulsante
      const btnAdd = el('btnAddIngredientRow');
      if (btnAdd) {
        btnAdd.addEventListener('click', addIngredientRow);
      }
    });

    // Initialize subscription UI
    if (typeof initSubscriptionUI === 'function') {
      initSubscriptionUI();
    }

    // Se pywebview segnala readiness, usa quello. Altrimenti fallback su DOMContentLoaded/poll.
    document.addEventListener('pywebviewready', initWhenReady);
    document.addEventListener('DOMContentLoaded', () => {
      if (!initStarted) initWhenReady();
    });

    // Poll leggero nel caso l'evento non arrivi (alcune versioni non lo emettono).
    let apiPollTries = 0;
    const apiPoll = () => {
      if (apiReady()) {
        initWhenReady();
        return;
      }
      if (apiPollTries++ < 20) {
        setTimeout(apiPoll, 250);
      } else {
        const pv = el('pillValue');
        if (pv) pv.textContent = 'API non disponibile';
        showToast('API non disponibile. Riavvia l\'app o reinstalla WebView2.', 'error', 6000);
      }
    };
    apiPoll();

    // ===== PWA: Register Service Worker =====
    if ('serviceWorker' in navigator && window.location.protocol === 'https:') {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('/service-worker.js')
          .then((reg) => {
            console.log('[PWA] Service Worker registered:', reg);
            // Check for updates periodically
            setInterval(() => {
              reg.update().catch(() => { });
            }, 60 * 60 * 1000); // Ogni ora
          })
          .catch((err) => {
            console.warn('[PWA] Service Worker registration failed:', err);
          });
      });

      // Notifica utente quando update disponibile
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        showToast('Aggiornamento disponibile! Ricarica la pagina.', 'info', 5000);
      });
    }

    debugLog('[COOKSY] initWhenReady scheduled');
  } ());
