import React, { useState, useEffect, useMemo } from "react";
import { getTargetFeatures, expandQuery } from "../services/search.js";

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
  activePreset = "default",
  onSelectPreset,
}) {
  const [showPrefixMenu, setShowPrefixMenu] = useState(false);
  const [targetFeatures, setTargetFeatures] = useState([]);

  // State cho Query Expansion, Google-style Suggestion & Jina Auto-Fusion
  const [isExpanding, setIsExpanding] = useState(false);
  const [autoFusion, setAutoFusion] = useState(false);
  const [expansionVariants, setExpansionVariants] = useState([]);
  const [expansionError, setExpansionError] = useState("");
  const [suggestionInfo, setSuggestionInfo] = useState(null);
  const [showVariants, setShowVariants] = useState(false);
  const [forceOriginal, setForceOriginal] = useState(false);

  // State đóng/mở 2 bộ lọc bên cạnh (OCR/ASR Filters & Video Filters)
  const [showOcrAsrPanel, setShowOcrAsrPanel] = useState(true);
  const [showVideoPanel, setShowVideoPanel] = useState(true);

  // Helper to parse OCR and ASR tags out of full query string
  const parseQuery = (queryString) => {
    let mainText = queryString || "";
    let ocrText = "";
    let asrText = "";

    // Parse [OCR:"..."] or [OCR:text]
    const ocrRegex = /\s?\[OCR:((".*?")|[^\]]+)\]/gi;
    const ocrMatch = ocrRegex.exec(mainText);
    if (ocrMatch) {
      ocrText = ocrMatch[1].trim();
      mainText = mainText.replace(ocrMatch[0], "");
    }

    // Parse [asr:"..."] or [asr:text]
    const asrRegex = /\s?\[asr:((".*?")|[^\]]+)\]/gi;
    const asrMatch = asrRegex.exec(mainText);
    if (asrMatch) {
      asrText = asrMatch[1].trim();
      mainText = mainText.replace(asrMatch[0], "");
    }

    return { mainText: mainText.trim(), ocrText, asrText };
  };

  // Helper to rebuild query string from main, ocr, and asr inputs
  const buildQuery = (mainText, ocrText, asrText) => {
    let parts = [mainText.trim()];
    if (ocrText.trim()) {
      parts.push(`[OCR:${ocrText.trim()}]`);
    }
    if (asrText.trim()) {
      parts.push(`[asr:${asrText.trim()}]`);
    }
    return parts.filter(Boolean).join(" ");
  };

  const parsed = useMemo(() => parseQuery(q), [q]);

  const [mainQuery, setMainQuery] = useState(parsed.mainText);
  const [ocrQuery, setOcrQuery] = useState(parsed.ocrText);
  const [asrQuery, setAsrQuery] = useState(parsed.asrText);

  // Auto-Search toggle state (persisted in localStorage)
  const [autoSearch, setAutoSearch] = useState(() => {
    const saved = localStorage.getItem("vecna_auto_search");
    return saved !== null ? JSON.parse(saved) : true;
  });

  // Check if mainQuery has temporal delimiters \ or /
  const hasTemporal = /[\/\\\\]/.test(mainQuery);

  // Extract delimiter used (/ or \)
  const temporalDelimiter = useMemo(() => {
    if (mainQuery.includes("/")) return "/";
    return "\\";
  }, [mainQuery]);

  // Split mainQuery into non-delimiter segment strings
  const temporalSegments = useMemo(() => {
    if (!hasTemporal) return [];
    return mainQuery.split(/[\/\\\\]/);
  }, [mainQuery, hasTemporal]);

  const handleUpdateTemporalSegment = (stepIdx, newText) => {
    const currentSegments = mainQuery.split(/[\/\\\\]/);
    currentSegments[stepIdx] = newText;
    setMainQuery(currentSegments.join(temporalDelimiter));
  };

  // Sync state if external q changes
  useEffect(() => {
    const p = parseQuery(q);
    setMainQuery(p.mainText);
    setOcrQuery(p.ocrText);
    setAsrQuery(p.asrText);
  }, [q]);

  // Debounced live search trigger (only when autoSearch is true)
  useEffect(() => {
    if (!autoSearch) return;
    const timer = setTimeout(async () => {
      const trimmed = mainQuery.trim();
      if (!trimmed) {
        setSuggestionInfo(null);
        setShowVariants(false);
        const fullQuery = buildQuery("", ocrQuery, asrQuery);
        if (fullQuery !== q) onChange(fullQuery);
        return;
      }

      if (forceOriginal) {
        setSuggestionInfo(null);
        const fullQuery = buildQuery(trimmed, ocrQuery, asrQuery);
        if (fullQuery !== q) onChange(fullQuery);
        return;
      }

      // Auto spellcheck / HyDE check in background without overwriting textarea
      if (autoFusion && !isExpanding) {
        try {
          const res = await expandQuery(trimmed);
          if (res && res.detailed) {
            const corrected = res.detailed.corrected || res.detailed.hyde || trimmed;
            if (corrected.toLowerCase() !== trimmed.toLowerCase()) {
              setSuggestionInfo({ original: trimmed, corrected });
              const fullQuery = buildQuery(corrected, ocrQuery, asrQuery);
              onChange(fullQuery);
              return;
            }
          }
        } catch (e) {
          console.error("Auto spellcheck error:", e);
        }
      }

      setSuggestionInfo(null);
      const fullQuery = buildQuery(trimmed, ocrQuery, asrQuery);
      if (fullQuery !== q) onChange(fullQuery);
    }, 500);
    return () => clearTimeout(timer);
  }, [mainQuery, ocrQuery, asrQuery, autoSearch, autoFusion, forceOriginal]);

  const [incInput, setIncInput] = useState(includeVideos || "");
  const [excInput, setExcInput] = useState(excludeVideos || "");

  useEffect(() => {
    setIncInput(includeVideos || "");
    setExcInput(excludeVideos || "");
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
      }
      handleApplyVideoFilters(nextVal, excInput);
    } else {
      const existing = excInput ? excInput.trim().split(/[,;\s]+/).filter(Boolean) : [];
      let nextVal = excInput;
      if (!existing.includes(prefixCode)) {
        nextVal = existing.length > 0 ? `${excInput.trim()}, ${prefixCode}` : prefixCode;
        setExcInput(nextVal);
      }
      handleApplyVideoFilters(incInput, nextVal);
    }
  };

  const handleExpandQuery = async () => {
    if (!mainQuery || !mainQuery.trim()) {
      setExpansionError("Please enter a search query before expanding.");
      return;
    }
    setIsExpanding(true);
    setExpansionError("");
    setExpansionVariants([]);
    setShowVariants(true);

    try {
      const res = await expandQuery(mainQuery.trim());
      if (res && res.error) {
        setExpansionError(res.error);
      } else if (!res || !res.variants || res.variants.length === 0) {
        setExpansionError("Failed to expand query (check GROQ_API_KEY).");
      } else {
        setExpansionVariants(res.variants);
      }
    } catch (err) {
      console.error("Error expanding query:", err);
      setExpansionError("GROQ_API_KEY is not configured in workspace/config.yaml (or GROQ_API_KEY environment variable)");
    } finally {
      setIsExpanding(false);
    }
  };

  const handleSelectExpansionVariant = (variantText) => {
    setMainQuery(variantText);
    setShowVariants(false);
    setSuggestionInfo(null);
    setExpansionVariants([]);
    setExpansionError("");
    const fullQuery = buildQuery(variantText, ocrQuery, asrQuery);
    onChange(fullQuery);
  };

  const handleMainQueryKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const fullQuery = buildQuery(mainQuery, ocrQuery, asrQuery);
      onChange(fullQuery);
    }
  };

  return (
    <div className="w-full flex flex-col lg:flex-row gap-2 bg-sky-200 border border-sky-300 p-2 rounded-lg shadow-sm mb-2">
      {/* Primary Text Search Query Box */}
      <div className="flex-1 flex flex-col gap-1.5 h-full">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {/* Auto-Search Toggle Button */}
            <button
              type="button"
              onClick={() => setAutoSearch(!autoSearch)}
              className={`text-[11px] font-semibold px-2 py-0.5 rounded border transition-all flex items-center gap-1.5 shadow-sm ${
                autoSearch
                  ? "bg-emerald-600 hover:bg-emerald-700 text-white border-emerald-700"
                  : "bg-gray-100 hover:bg-gray-200 text-gray-700 border-gray-300"
              }`}
              title={
                autoSearch
                  ? "Auto-search enabled (searches 500ms after typing). Click to turn OFF."
                  : "Manual search enabled (Press Enter to search). Click to turn ON auto-search."
              }
            >
              <span className={`w-2 h-2 rounded-full ${autoSearch ? "bg-white animate-pulse" : "bg-gray-400"}`}></span>
              Auto-Search: {autoSearch ? "ON" : "OFF"}
            </button>

            {!autoSearch && (
              <button
                type="button"
                onClick={() => {
                  const fullQuery = buildQuery(mainQuery, ocrQuery, asrQuery);
                  onChange(fullQuery);
                }}
                className="text-[11px] font-bold px-2 py-0.5 rounded bg-blue-600 hover:bg-blue-700 text-white shadow-sm flex items-center gap-1 transition-colors"
                title="Run search (or press Enter)"
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                Search (Enter)
              </button>
            )}

            <button
              type="button"
              onClick={handleExpandQuery}
              disabled={isExpanding}
              className={`text-[11px] font-bold px-2.5 py-0.5 rounded border transition-all shadow-sm flex items-center gap-1.5 cursor-pointer ${
                isExpanding
                  ? "bg-purple-300 text-purple-900 border-purple-400 cursor-wait animate-pulse"
                  : "bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white border-purple-700 hover:shadow"
              }`}
              title="Click to expand query into 3 visual search variants (Corrected, HyDE, Paraphrase)"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              {isExpanding ? "Expanding..." : "Expand Query"}
            </button>

            {/* Jina Auto-Fusion Toggle Button */}
            <button
              type="button"
              onClick={() => setAutoFusion(!autoFusion)}
              className={`text-[11px] font-semibold px-2 py-0.5 rounded border transition-all flex items-center gap-1 shadow-sm cursor-pointer ${
                autoFusion
                  ? "bg-purple-600 hover:bg-purple-700 text-white border-purple-700 font-bold"
                  : "bg-gray-100 hover:bg-gray-200 text-gray-700 border-gray-300"
              }`}
              title={
                autoFusion
                  ? "Auto-Fusion ENABLED: Auto spell-checks and searches HyDE in background. Click to turn OFF."
                  : "Auto-Fusion DISABLED: Manual expansion mode. Click to turn ON auto-fusion."
              }
            >
              <span className={`w-2 h-2 rounded-full ${autoFusion ? "bg-white animate-ping" : "bg-gray-400"}`}></span>
              Auto-Fusion: {autoFusion ? "ON" : "OFF"}
            </button>

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

            {isSearching && (
              <span className="text-xs text-sky-800 font-semibold animate-pulse ml-1">
                Searching...
              </span>
            )}

          </div>
        </div>

        <textarea
          data-query-input="main"
          className={`w-full text-sm bg-white text-gray-900 border border-sky-400 rounded p-2 focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none font-sans transition-all flex-1 h-full min-h-[80px] max-h-48 overflow-y-auto`}
          rows={hasTemporal ? 2 : 3}
          placeholder="Type search text here... (Temporal syntax: '\\' or '/' for sequence)"
          value={mainQuery}
          onChange={(e) => {
            setMainQuery(e.target.value);
            setForceOriginal(false);
          }}
          onKeyDown={handleMainQueryKeyDown}
        />

        {/* Google-Style Spellcheck Suggestion Banner */}
        {suggestionInfo && (
          <div className="text-xs bg-white/95 border-l-4 border-blue-600 px-3 py-1.5 rounded shadow-xs flex flex-col gap-0.5 animate-fadeIn">
            <div className="text-gray-800 font-medium flex items-center gap-1 flex-wrap">
              Showing results for{" "}
              <button
                type="button"
                onClick={() => {
                  setMainQuery(suggestionInfo.corrected);
                  setSuggestionInfo(null);
                  const fullQuery = buildQuery(suggestionInfo.corrected, ocrQuery, asrQuery);
                  onChange(fullQuery);
                }}
                className="font-bold text-blue-900 italic underline hover:text-blue-700 cursor-pointer max-w-full truncate"
                title="Click to replace search box text with corrected query"
              >
                "{suggestionInfo.corrected}"
              </button>
            </div>
            <div className="text-gray-600 text-[11px] flex items-center gap-1 flex-wrap">
              Search instead for{" "}
              <button
                type="button"
                onClick={() => {
                  setForceOriginal(true);
                  setSuggestionInfo(null);
                  const fullQuery = buildQuery(suggestionInfo.original, ocrQuery, asrQuery);
                  onChange(fullQuery);
                }}
                className="text-blue-600 hover:text-blue-800 underline font-semibold cursor-pointer max-w-full truncate"
              >
                "{suggestionInfo.original}"
              </button>
            </div>
          </div>
        )}

        {/* 3 Expansion Variant Dropdown Cards (Shown ONLY when Expand Query is clicked) */}
        {expansionError && (
          <div className="text-xs text-red-600 font-semibold bg-red-50 border border-red-200 px-2 py-1 rounded">
            {expansionError}
          </div>
        )}

        {showVariants && expansionVariants.length > 0 && (
          <div className="flex flex-col gap-2 bg-white/95 border border-purple-300 p-2.5 rounded-lg shadow-sm animate-fadeIn w-full max-w-full min-w-0 overflow-hidden">
            <div className="flex items-center justify-between min-w-0">
              <span className="text-[10px] font-bold text-purple-900 uppercase tracking-wider flex items-center gap-1 truncate min-w-0">
                <span className="w-1.5 h-1.5 rounded-full bg-purple-600 animate-ping shrink-0"></span>
                <span className="truncate">Jina AI Expansion Variants (Click card to search):</span>
              </span>
              <button
                type="button"
                onClick={() => setShowVariants(false)}
                className="text-xs text-gray-500 hover:text-gray-700 font-bold px-1 shrink-0 cursor-pointer"
                title="Close variants"
              >
                ✕
              </button>
            </div>
            <div className="flex flex-col gap-2 pt-0.5 w-full max-w-full min-w-0">
              {expansionVariants.map((variant, idx) => {
                const labels = ["Corrected", "HyDE", "Paraphrase"];
                const label = labels[idx] || `Variant ${idx + 1}`;
                const badgeColors = [
                  "bg-purple-50 hover:bg-purple-100 text-purple-950 border-purple-300",
                  "bg-emerald-50 hover:bg-emerald-100 text-emerald-950 border-emerald-300",
                  "bg-indigo-50 hover:bg-indigo-100 text-indigo-950 border-indigo-300",
                ];
                const badgeColor = badgeColors[idx % badgeColors.length];

                return (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => handleSelectExpansionVariant(variant)}
                    className={`w-full max-w-full min-w-0 text-xs p-2 rounded-md border transition-all shadow-xs flex flex-col gap-1 cursor-pointer text-left hover:scale-[1.002] active:scale-98 ${badgeColor}`}
                    title={`Click to select and search: "${variant}"`}
                  >
                    <div className="flex items-center justify-between w-full min-w-0">
                      <span className="font-extrabold text-[11px] uppercase tracking-wide opacity-90">{label}:</span>
                      <span className="text-[10px] opacity-60 font-normal">Click to search</span>
                    </div>
                    <div className="w-full max-h-16 overflow-y-auto whitespace-normal break-words pr-1 scrollbar-thin scrollbar-thumb-purple-400 scrollbar-track-transparent text-xs font-medium leading-relaxed">
                      "{variant}"
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Dynamic Full-Width Interactive Temporal Step Inputs (Rendered ONLY when hasTemporal is true) */}
        {hasTemporal && (
          <div className="flex flex-col gap-1.5 pt-1 border-t border-sky-300 w-full animate-fadeIn">
            {temporalSegments.map((segmentText, stepIdx) => (
              <div
                key={stepIdx}
                className="flex items-center bg-white border border-sky-400 px-2 py-1 rounded-lg text-xs font-semibold text-sky-950 font-mono shadow-sm focus-within:ring-1 focus-within:ring-blue-500 w-full"
              >
                <span className="text-[10px] text-sky-600 font-bold mr-1.5 shrink-0 select-none">
                  #{stepIdx + 1}
                </span>
                <input
                  type="text"
                  value={segmentText}
                  onChange={(e) => handleUpdateTemporalSegment(stepIdx, e.target.value)}
                  onKeyDown={handleMainQueryKeyDown}
                  className="bg-transparent text-xs font-mono font-bold text-sky-950 focus:outline-none w-full"
                  placeholder={`Step ${stepIdx + 1} text...`}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Dedicated OCR & ASR Filters Panel */}
      {showOcrAsrPanel && (
        <div className="w-full lg:w-56 shrink-0 flex flex-col gap-1.5 bg-white border border-sky-300 p-2 rounded shadow-sm animate-fadeIn">
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
              onChange={(e) => setOcrQuery(e.target.value)}
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
              onChange={(e) => setAsrQuery(e.target.value)}
              onKeyDown={handleMainQueryKeyDown}
            />
          </div>
        </div>
      )}

      {/* Dedicated Include / Exclude Video Filter Panel with Header Menu */}
      {showVideoPanel && (
        <div className="w-full lg:w-56 shrink-0 flex flex-col gap-1.5 bg-white border border-sky-300 p-2 rounded shadow-sm relative animate-fadeIn">
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
          <div className="flex items-center justify-between pt-1 mt-auto">
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
