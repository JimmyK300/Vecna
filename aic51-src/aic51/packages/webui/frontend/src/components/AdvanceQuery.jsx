import React, { useState, useEffect, useMemo, useRef } from "react";

const VIDEO_PREFIX_OPTIONS = [
  { prefix: "L21", name: "L21: HTV 60 Seconds (P1)" },
  { prefix: "L22", name: "L22: HTV 60 Seconds (P2)" },
  { prefix: "L23", name: "L23: HTV Cycling Cup 2024" },
  { prefix: "L24", name: "L24: Lion Dance - Cho Lon Cup" },
  { prefix: "L25", name: "L25: TN News - Exam 2024" },
  { prefix: "L26", name: "L26: Daily Delicious Dishes" },
  { prefix: "L27", name: "L27: Vietnam Travel S3" },
  { prefix: "L28", name: "L28: Mekong Ramblings" },
  { prefix: "L29", name: "L29: Eyes of Mekong" },
  { prefix: "L30", name: "L30: Tuoi Tre News 2024" },
];

/**
 * Helper to parse a single segment string into { visual, ocr, asr }
 */
export const parseSegment = (segmentStr = "") => {
  let visual = segmentStr || "";
  let ocr = "";
  let asr = "";

  // Parse [OCR:"..."] or [OCR:text]
  const ocrRegex = /\s?\[OCR:\s*([^\]]*)\]/i;
  const ocrMatch = ocrRegex.exec(visual);
  if (ocrMatch) {
    ocr = (ocrMatch[1] || "").trim();
    visual = visual.replace(ocrMatch[0], "");
  }

  // Parse [asr:"..."], [speech:"..."], [asr:text], or [speech:text]
  const asrRegex = /\s?\[(?:asr|speech):\s*([^\]]*)\]/i;
  const asrMatch = asrRegex.exec(visual);
  if (asrMatch) {
    asr = (asrMatch[1] || "").trim();
    visual = visual.replace(asrMatch[0], "");
  }

  return { visual: visual.trim(), ocr: ocr.trim(), asr: asr.trim() };
};

/**
 * Helper to build a single segment string from { visual, ocr, asr }
 */
export const buildSegment = ({ visual = "", ocr = "", asr = "" }) => {
  const parts = [];
  if (visual && visual.trim()) {
    parts.push(visual.trim());
  }
  if (ocr && ocr.trim()) {
    parts.push(`[OCR:${ocr.trim()}]`);
  }
  if (asr && asr.trim()) {
    parts.push(`[asr:${asr.trim()}]`);
  }
  return parts.join(" ");
};

/**
 * Helper to rebuild full multi-segment query from segments array
 */
export const buildFullQuery = (segments, delimiter = "\n") => {
  if (!segments || segments.length === 0) return "";
  if (segments.length === 1) {
    return buildSegment(segments[0]);
  }
  return segments.map((s) => buildSegment(s)).join(delimiter);
};

export function AdvanceQueryContainer({
  q = "",
  onChange,
  autoTranslate = false,
  onToggleAutoTranslate,
  includeVideos = "",
  onIncludeVideosChange,
  excludeVideos = "",
  onExcludeVideosChange,
  onApplyVideoFilters,
  isSearching = false,
  onCancelSearch,
  activePreset = "default",
  onSelectPreset,
  onResetQueryHeight,
  translationFailed = false,
  collection = "workspace",
  onCollectionChange,
}) {
  const [showPrefixMenu, setShowPrefixMenu] = useState(false);

  // State thông báo lỗi dịch tự động dưới thanh query
  const [showTranslateErrorToast, setShowTranslateErrorToast] = useState(false);

  useEffect(() => {
    if (translationFailed && autoTranslate) {
      setShowTranslateErrorToast(true);
      const timer = setTimeout(() => {
        setShowTranslateErrorToast(false);
      }, 1800);
      return () => clearTimeout(timer);
    }
  }, [translationFailed, autoTranslate]);

  // State đóng/mở 2 bộ lọc bên cạnh (OCR/ASR Filters & Video Filters)
  const [showOcrAsrPanel, setShowOcrAsrPanel] = useState(() => !/\r?\n/.test(q || ""));
  const [showVideoPanel, setShowVideoPanel] = useState(true);

  // Main active query string in input box
  const [mainQuery, setMainQuery] = useState(q || "");

  // Auto-Search toggle state (persisted in localStorage)
  const [autoSearch, setAutoSearch] = useState(() => {
    const saved = localStorage.getItem("vecna_auto_search");
    return saved !== null ? JSON.parse(saved) : true;
  });

  // Each non-empty line is one temporal event.
  const hasTemporal = /\r?\n/.test(mainQuery);

  // Auto-close OCR/ASR panel when entering temporal search mode, restore when leaving
  const prevHasTemporalRef = useRef(hasTemporal);
  useEffect(() => {
    if (hasTemporal) {
      setShowOcrAsrPanel(false);
    } else if (prevHasTemporalRef.current) {
      setShowOcrAsrPanel(true);
    }
    prevHasTemporalRef.current = hasTemporal;
  }, [hasTemporal]);

  const temporalDelimiter = "\n";

  // Split mainQuery into parsed segment objects { visual, ocr, asr }
  const temporalSegments = useMemo(() => {
    if (!hasTemporal) {
      return [parseSegment(mainQuery)];
    }
    const rawSegments = mainQuery.split(/\r?\n/);
    return rawSegments.map((seg) => parseSegment(seg));
  }, [mainQuery, hasTemporal]);

  // Global OCR/ASR values for single query mode
  const singleParsed = useMemo(() => parseSegment(mainQuery), [mainQuery]);
  const [ocrQuery, setOcrQuery] = useState(singleParsed.ocr);
  const [asrQuery, setAsrQuery] = useState(singleParsed.asr);

  useEffect(() => {
    setOcrQuery(singleParsed.ocr);
    setAsrQuery(singleParsed.asr);
  }, [singleParsed.ocr, singleParsed.asr]);

  const lastSubmittedRef = useRef("");

  // Sync state if external q changes (never overwrite mainQuery if user is actively typing)
  useEffect(() => {
    if (!mainQuery || !mainQuery.trim()) {
      setMainQuery(q || "");
    }
  }, [q]);

  // Update a specific field (visual, ocr, asr) of step stepIdx
  const handleUpdateTemporalField = (stepIdx, field, value) => {
    const currentSegments = hasTemporal
      ? mainQuery.split(/\r?\n/).map((s) => parseSegment(s))
      : [parseSegment(mainQuery)];

    while (currentSegments.length <= stepIdx) {
      currentSegments.push({ visual: "", ocr: "", asr: "" });
    }

    currentSegments[stepIdx] = {
      ...currentSegments[stepIdx],
      [field]: value,
    };

    const newFullQuery = buildFullQuery(currentSegments, temporalDelimiter);
    setMainQuery(newFullQuery);
  };


  // Update side panel OCR query (for single query mode)
  const handleSideOcrChange = (newOcr) => {
    setOcrQuery(newOcr);
    if (!hasTemporal) {
      const single = parseSegment(mainQuery);
      single.ocr = newOcr;
      setMainQuery(buildSegment(single));
    } else {
      handleUpdateTemporalField(0, "ocr", newOcr);
    }
  };

  // Update side panel ASR query (for single query mode)
  const handleSideAsrChange = (newAsr) => {
    setAsrQuery(newAsr);
    if (!hasTemporal) {
      const single = parseSegment(mainQuery);
      single.asr = newAsr;
      setMainQuery(buildSegment(single));
    } else {
      handleUpdateTemporalField(0, "asr", newAsr);
    }
  };

  // Debounced live search trigger (only when autoSearch is true)
  useEffect(() => {
    if (!autoSearch) return;
    const timer = setTimeout(() => {
      const trimmed = mainQuery.trim();
      if (!trimmed) {
        lastSubmittedRef.current = "";
        if (q !== "") onChange("");
        return;
      }

      lastSubmittedRef.current = trimmed;
      if (trimmed !== q) onChange(trimmed);
    }, 450);
    return () => clearTimeout(timer);
  }, [mainQuery, autoSearch, q]);

  const [incInput, setIncInput] = useState(includeVideos || "");
  const [excInput, setExcInput] = useState(excludeVideos || "");

  useEffect(() => {
    setIncInput(includeVideos || "");
    setExcInput(excludeVideos || "");
    if (includeVideos || excludeVideos) {
      setShowVideoPanel(true);
    }
  }, [includeVideos, excludeVideos]);

  const handleApplyVideoFilters = (newInc = incInput, newExc = excInput) => {
    if (onApplyVideoFilters) {
      onApplyVideoFilters(newInc, newExc);
    } else {
      onIncludeVideosChange && onIncludeVideosChange(newInc);
      onExcludeVideosChange && onExcludeVideosChange(newExc);
    }
  };

  const handleClearVideoFilters = () => {
    setIncInput("");
    setExcInput("");
    handleApplyVideoFilters("", "");
  };

  const handleVideoFilterKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleApplyVideoFilters();
    }
  };

  const handleAddDirectPrefix = (prefixCode, type) => {
    if (!prefixCode) return;
    if (type === "include") {
      const existing = incInput ? incInput.trim().split(/[,;\s]+/).filter(Boolean) : [];
      let nextVal = incInput;
      if (!existing.includes(prefixCode)) {
        nextVal = existing.length > 0 ? `${incInput.trim()}, ${prefixCode}` : prefixCode;
        setIncInput(nextVal);
        onIncludeVideosChange && onIncludeVideosChange(nextVal);
      }
    } else {
      const existing = excInput ? excInput.trim().split(/[,;\s]+/).filter(Boolean) : [];
      let nextVal = excInput;
      if (!existing.includes(prefixCode)) {
        nextVal = existing.length > 0 ? `${excInput.trim()}, ${prefixCode}` : prefixCode;
        setExcInput(nextVal);
        onExcludeVideosChange && onExcludeVideosChange(nextVal);
      }
    }
  };

  const triggerManualSearch = () => {
    const trimmed = mainQuery.trim();
    if (!trimmed) {
      lastSubmittedRef.current = "";
      onChange("");
      return;
    }

    lastSubmittedRef.current = trimmed;
    onChange(trimmed);
  };

  const handleMainQueryKeyDown = (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      triggerManualSearch();
    }
  };

  return (
    <div className="w-full flex flex-col lg:flex-row gap-2 bg-sky-200 border border-sky-300 p-2 rounded-lg shadow-sm mb-2">
      {/* Primary Text Search Query Box */}
      <div className="flex-1 flex flex-col gap-1.5 min-w-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 flex-wrap">
            {/* Auto-Search Toggle Button */}
            <button
              type="button"
              onClick={() => {
                const next = !autoSearch;
                setAutoSearch(next);
                try {
                  localStorage.setItem("vecna_auto_search", JSON.stringify(next));
                } catch (e) {}
              }}
              className={`text-[11px] font-semibold px-2 py-0.5 rounded border transition-all flex items-center gap-1.5 shadow-sm cursor-pointer ${
                autoSearch
                  ? "bg-emerald-600 hover:bg-emerald-700 text-white border-emerald-700"
                  : "bg-gray-100 hover:bg-gray-200 text-gray-700 border-gray-300"
              }`}
              title={
                autoSearch
                  ? "Auto-search enabled (searches 450ms after typing). Click to turn OFF."
                  : "Manual search enabled (Press Ctrl+Enter to search). Enter creates a temporal event."
              }
            >
              <span className={`w-2 h-2 rounded-full ${autoSearch ? "bg-white animate-pulse" : "bg-gray-400"}`}></span>
              Auto-Search: {autoSearch ? "ON" : "OFF"}
            </button>

            {isSearching ? (
              <button
                type="button"
                onClick={onCancelSearch}
                className="text-[11px] font-bold px-2.5 py-0.5 rounded bg-rose-600 hover:bg-rose-700 text-white shadow-sm flex items-center gap-1.5 transition-colors cursor-pointer animate-pulse"
                title="Cancel / Stop current search"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                </svg>
                Cancel (Stop)
              </button>
            ) : (
              !autoSearch && (
                <button
                  type="button"
                  onClick={triggerManualSearch}
                  className="text-[11px] font-bold px-2 py-0.5 rounded bg-blue-600 hover:bg-blue-700 text-white shadow-sm flex items-center gap-1 transition-colors cursor-pointer"
                  title="Run search (or press Ctrl+Enter)"
                >
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  Search (Ctrl+Enter)
                </button>
              )
            )}


            {/* OCR/ASR Filter Panel Toggle */}
            <button
              type="button"
              onClick={() => setShowOcrAsrPanel(!showOcrAsrPanel)}
              className={`text-[11px] font-semibold px-2 py-0.5 rounded border transition-all flex items-center gap-1 shadow-sm cursor-pointer ${
                showOcrAsrPanel
                  ? "bg-amber-600 hover:bg-amber-700 text-white border-amber-700"
                  : "bg-gray-100 hover:bg-gray-200 text-gray-700 border-gray-300"
              }`}
              title="Click to show / hide OCR & ASR Filters side panel"
            >
              <span className={`w-2 h-2 rounded-full ${showOcrAsrPanel ? "bg-white" : "bg-gray-400"}`}></span>
              OCR/ASR: {showOcrAsrPanel ? "ON" : "OFF"}
            </button>

            {/* Video Filters Panel Toggle */}
            <button
              type="button"
              onClick={() => setShowVideoPanel(!showVideoPanel)}
              className={`text-[11px] font-semibold px-2 py-0.5 rounded border transition-all flex items-center gap-1 shadow-sm cursor-pointer ${
                showVideoPanel
                  ? "bg-emerald-600 hover:bg-emerald-700 text-white border-emerald-700"
                  : "bg-gray-100 hover:bg-gray-200 text-gray-700 border-gray-300"
              }`}
              title="Click to show / hide Video Filters side panel"
            >
              <span className={`w-2 h-2 rounded-full ${showVideoPanel ? "bg-white" : "bg-gray-400"}`}></span>
              Video Filters: {showVideoPanel ? "ON" : "OFF"}
            </button>

            {/* Batch Selector (Batch 1: L,S,M vs Batch 2: N vs All) */}
            <div className="flex items-center bg-gray-100 p-0.5 rounded border border-gray-300 shadow-2xs ml-1 gap-0.5">
              <button
                type="button"
                onClick={() => onCollectionChange && onCollectionChange("workspace")}
                className={`px-2 py-0.5 text-[11px] font-bold rounded transition-all cursor-pointer flex items-center gap-1 ${
                  collection === "workspace" || collection === "testcol1" || collection === "1"
                    ? "bg-blue-600 text-white shadow-xs font-black"
                    : "text-gray-700 hover:text-blue-700 hover:bg-blue-50"
                }`}
                title="Chỉ tìm kiếm trong Batch 1 (Workspace: Video mã L, S, M)"
              >
                <span>📦 Batch 1 (L, S, M)</span>
              </button>

              <button
                type="button"
                onClick={() => onCollectionChange && onCollectionChange("workspace2")}
                className={`px-2 py-0.5 text-[11px] font-bold rounded transition-all cursor-pointer flex items-center gap-1 ${
                  collection === "workspace2" || collection === "testcol2" || collection === "2"
                    ? "bg-purple-600 text-white shadow-xs font-black"
                    : "text-gray-700 hover:text-purple-700 hover:bg-purple-50"
                }`}
                title="Chỉ tìm kiếm trong Batch 2 (Workspace 2: Video mã N)"
              >
                <span>📦 Batch 2 (N)</span>
              </button>

              <button
                type="button"
                onClick={() => onCollectionChange && onCollectionChange("all")}
                className={`px-2 py-0.5 text-[11px] font-bold rounded transition-all cursor-pointer flex items-center gap-1 ${
                  collection === "all"
                    ? "bg-gray-800 text-white shadow-xs font-black"
                    : "text-gray-500 hover:text-gray-900 hover:bg-gray-200"
                }`}
                title="Tìm kiếm cả 2 Batch (Đan xen kết quả)"
              >
                <span>🌐 Cả hai</span>
              </button>
            </div>

            {isSearching && (
              <span className="text-xs text-sky-800 font-semibold animate-pulse ml-1">
                Searching...
              </span>
            )}
          </div>
        </div>

        {/* Primary Query Textarea */}
        <textarea
          data-query-input="main"
          spellCheck={false}
          autoCorrect="off"
          autoCapitalize="off"
          className="w-full text-xs bg-white text-gray-900 border border-sky-400 rounded p-2 focus:outline-none focus:ring-1 focus:ring-blue-500 font-sans transition-all min-h-[48px] max-h-64 overflow-y-auto leading-relaxed resize-y"
          rows={3}
          placeholder="Type search text here... (Temporal: one event per line; [OCR: text], [asr: speech])"
          value={mainQuery}
          onChange={(e) => {
            setMainQuery(e.target.value);
          }}
          onKeyDown={handleMainQueryKeyDown}
        />

        {/* Translation Error Toast Notification (Auto-dismisses in ~1.8s) */}
        {showTranslateErrorToast && (
          <div className="text-[11px] bg-rose-50 text-rose-800 border border-rose-300 px-2.5 py-1 rounded shadow-xs flex items-center justify-between gap-2 animate-fadeIn transition-all">
            <div className="flex items-center gap-1.5 font-medium">
              <svg className="w-3.5 h-3.5 text-rose-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <span>Dịch tự động thất bại (Google Translate bị sập/Rate limit). Đang tìm kiếm bằng câu gốc.</span>
            </div>
            <button
              type="button"
              onClick={() => setShowTranslateErrorToast(false)}
              className="text-rose-500 hover:text-rose-700 font-bold text-xs cursor-pointer px-1"
              title="Đóng thông báo"
            >
              ✕
            </button>
          </div>
        )}



        {/* Minimal Compact Interactive Temporal Multi-Step Inputs */}
        {hasTemporal && (
          <div className="flex flex-col gap-1.5 pt-1.5 border-t border-sky-300 w-full animate-fadeIn">
            {temporalSegments.map((segment, stepIdx) => (
              <div
                key={stepIdx}
                className="flex flex-col gap-1 bg-white/95 border border-sky-300 rounded-md p-1.5 shadow-xs"
              >
                {/* Step Label on Top */}
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono font-bold text-sky-900 select-none">
                    Step #{stepIdx + 1}
                  </span>
                </div>

                {/* 3 Columns: Text/Visual (60%), OCR (20%), ASR (20%) with Labels on Top */}
                <div className="grid grid-cols-1 md:grid-cols-12 gap-1.5">
                  {/* Visual / Text Query */}
                  <div className="md:col-span-6 flex flex-col gap-0.5">
                    <span className="text-[9px] font-bold text-sky-800 flex items-center gap-1 select-none">
                      <span className="w-1.5 h-1.5 rounded-full bg-sky-500"></span>
                      Text / Visual:
                    </span>
                    <textarea
                      rows={1}
                      value={segment.visual}
                      onChange={(e) =>
                        handleUpdateTemporalField(stepIdx, "visual", e.target.value)
                      }
                      onKeyDown={handleMainQueryKeyDown}
                      className="w-full bg-sky-50/50 border border-sky-300 focus:border-sky-600 rounded px-2 py-1 text-xs text-gray-900 focus:outline-none focus:bg-white transition-all font-sans resize-y min-h-[28px] max-h-24 leading-relaxed overflow-y-auto"
                      placeholder={`Step #${stepIdx + 1} text...`}
                    />
                  </div>

                  {/* OCR Text */}
                  <div className="md:col-span-3 flex flex-col gap-0.5">
                    <span className="text-[9px] font-bold text-amber-800 flex items-center gap-1 select-none">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
                      OCR:
                    </span>
                    <textarea
                      rows={1}
                      value={segment.ocr}
                      onChange={(e) =>
                        handleUpdateTemporalField(stepIdx, "ocr", e.target.value)
                      }
                      onKeyDown={handleMainQueryKeyDown}
                      className="w-full bg-amber-50/40 border border-amber-300 focus:border-amber-600 rounded px-1.5 py-1 text-xs text-gray-900 focus:outline-none focus:bg-white transition-all font-sans resize-y min-h-[28px] max-h-20 leading-relaxed overflow-y-auto"
                      placeholder="On-screen text"
                    />
                  </div>

                  {/* ASR Speech */}
                  <div className="md:col-span-3 flex flex-col gap-0.5">
                    <span className="text-[9px] font-bold text-purple-800 flex items-center gap-1 select-none">
                      <span className="w-1.5 h-1.5 rounded-full bg-purple-500"></span>
                      ASR:
                    </span>
                    <textarea
                      rows={1}
                      value={segment.asr}
                      onChange={(e) =>
                        handleUpdateTemporalField(stepIdx, "asr", e.target.value)
                      }
                      onKeyDown={handleMainQueryKeyDown}
                      className="w-full bg-purple-50/40 border border-purple-300 focus:border-purple-600 rounded px-1.5 py-1 text-xs text-gray-900 focus:outline-none focus:bg-white transition-all font-sans resize-y min-h-[28px] max-h-20 leading-relaxed overflow-y-auto"
                      placeholder="Audio speech"
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Dedicated OCR & ASR Filters Panel */}
      {showOcrAsrPanel && (
        <div className="w-full lg:w-56 shrink-0 flex flex-col gap-1.5 bg-white border border-sky-300 p-2 rounded shadow-sm self-start animate-fadeIn">
          <div className="flex items-center justify-between border-b border-gray-100 pb-1">
            <label className="text-xs font-bold text-gray-800 flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-amber-500"></span>
              OCR & ASR Filters
            </label>
            <button
              type="button"
              onClick={() => setShowOcrAsrPanel(false)}
              className="text-xs text-gray-400 hover:text-red-600 font-bold px-1 cursor-pointer"
              title="Close OCR/ASR Filters panel"
            >
              ✕
            </button>
          </div>

          <div className="flex flex-col gap-0.5">
            <span className="text-[10px] font-bold text-blue-700">OCR Text (On-screen):</span>
            <input
              type="text"
              data-query-input="ocr"
              className="w-full bg-slate-50 border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none focus:border-blue-500 font-sans"
              placeholder="e.g. Traffic Sign, Coffee"
              value={ocrQuery}
              onChange={(e) => handleSideOcrChange(e.target.value)}
              onKeyDown={handleMainQueryKeyDown}
            />
          </div>

          <div className="flex flex-col gap-0.5">
            <span className="text-[10px] font-bold text-purple-700">ASR Text (Audio Speech):</span>
            <input
              type="text"
              data-query-input="speech"
              className="w-full bg-slate-50 border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none focus:border-purple-500 font-sans"
              placeholder="e.g. Spoken words"
              value={asrQuery}
              onChange={(e) => handleSideAsrChange(e.target.value)}
              onKeyDown={handleMainQueryKeyDown}
            />
          </div>
        </div>
      )}

      {/* Dedicated Include / Exclude Video Filter Panel with Header Menu */}
      {showVideoPanel && (
        <div className="w-full lg:w-56 shrink-0 flex flex-col gap-1.5 bg-white border border-sky-300 p-2 rounded shadow-sm relative self-start animate-fadeIn">
          {/* Header Line with Prefix Menu Button Right Beside Video Filters */}
          <div className="flex items-center justify-between border-b border-gray-100 pb-1">
            <label className="text-xs font-bold text-gray-800 flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
              Video Filters
            </label>

            <div className="flex items-center gap-1">
              {/* Compact Prefix Menu Button */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setShowPrefixMenu(!showPrefixMenu)}
                  className="px-2 py-0.5 text-[11px] font-bold bg-slate-100 hover:bg-slate-200 border border-gray-300 rounded text-gray-800 flex items-center gap-1 shadow-sm transition-colors cursor-pointer"
                  title="Quick Select Prefix Code"
                >
                  Prefix ▾
                </button>

                {/* Popover Menu with + and - on EACH LINE */}
                {showPrefixMenu && (
                  <div
                    className="absolute top-full right-0 mt-1 z-40 bg-white border border-gray-300 rounded-lg shadow-xl p-1.5 w-60 max-h-64 overflow-y-auto font-sans"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="text-[10px] font-bold text-gray-500 px-1 pb-1 border-b mb-1 flex justify-between items-center">
                      <span>Select Prefix (+ Inc / - Exc):</span>
                      <button
                        onClick={() => setShowPrefixMenu(false)}
                        className="text-red-500 font-bold hover:text-red-700 text-xs px-1"
                      >
                        ✕
                      </button>
                    </div>

                    <div className="flex flex-col gap-1">
                      {VIDEO_PREFIX_OPTIONS.map((opt) => (
                        <div
                          key={opt.prefix}
                          className="flex items-center justify-between hover:bg-slate-50 p-1 rounded border border-gray-100 text-xs"
                        >
                          <span className="truncate text-[11px] font-medium text-gray-800 pr-1" title={opt.name}>
                            {opt.name}
                          </span>
                          <div className="flex items-center gap-1 shrink-0">
                            <button
                              type="button"
                              onClick={() => {
                                handleAddDirectPrefix(opt.prefix, "include");
                                setShowPrefixMenu(false);
                              }}
                              className="w-5 h-5 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded flex items-center justify-center text-xs shadow-sm cursor-pointer"
                              title={`Add ${opt.prefix} to Include`}
                            >
                              +
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                handleAddDirectPrefix(opt.prefix, "exclude");
                                setShowPrefixMenu(false);
                              }}
                              className="w-5 h-5 bg-red-600 hover:bg-red-700 text-white font-bold rounded flex items-center justify-center text-xs shadow-sm cursor-pointer"
                              title={`Add ${opt.prefix} to Exclude`}
                            >
                              -
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <button
                type="button"
                onClick={() => setShowVideoPanel(false)}
                className="text-xs text-gray-400 hover:text-red-600 font-bold px-1 cursor-pointer"
                title="Close Video Filters panel"
              >
                ✕
              </button>
            </div>
          </div>

          {/* Dual Input Fields for Include and Exclude Video Filters */}
          <div className="flex flex-col gap-1.5 pt-0.5">
            {/* 1. Include Input Box */}
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] font-bold text-emerald-700 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                Include Video IDs / Prefix:
              </span>
              <input
                type="text"
                className="w-full bg-slate-50 border border-emerald-300 focus:border-emerald-500 rounded px-2 py-1 text-xs focus:outline-none font-sans"
                placeholder="e.g. L21, L01_V001 (Press Enter ↵)"
                value={incInput}
                onChange={(e) => setIncInput(e.target.value)}
                onKeyDown={handleVideoFilterKeyDown}
              />
            </div>

            {/* 2. Exclude Input Box */}
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] font-bold text-rose-700 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-rose-500"></span>
                Exclude Video IDs / Prefix:
              </span>
              <input
                type="text"
                className="w-full bg-slate-50 border border-rose-300 focus:border-rose-500 rounded px-2 py-1 text-xs focus:outline-none font-sans"
                placeholder="e.g. L25, L02_V005 (Press Enter ↵)"
                value={excInput}
                onChange={(e) => setExcInput(e.target.value)}
                onKeyDown={handleVideoFilterKeyDown}
              />
            </div>
          </div>

          {/* Apply Filter & Clear Buttons */}
          <div className="flex items-center justify-between pt-1">
            <button
              type="button"
              onClick={handleClearVideoFilters}
              className="px-2 py-0.5 text-xs font-bold bg-slate-100 hover:bg-rose-100 text-slate-700 hover:text-rose-700 border border-slate-300 hover:border-rose-300 rounded transition-colors cursor-pointer shadow-xs flex items-center gap-1"
              title="Clear all video filters"
            >
              <span>Clear</span>
            </button>
            <button
              type="button"
              onClick={() => handleApplyVideoFilters()}
              className="px-2.5 py-1 text-xs font-bold bg-blue-600 hover:bg-blue-700 active:scale-95 text-white rounded flex items-center gap-1 shadow-sm transition-all cursor-pointer"
              title="Apply Video Filters (or press Enter in input)"
            >
              <span>Apply Filter</span>
              <span className="text-[10px] opacity-80 font-mono">↵</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
