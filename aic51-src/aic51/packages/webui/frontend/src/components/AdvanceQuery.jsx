import React, { useState, useEffect, useMemo } from "react";

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
  isSearching = false,
}) {
  const [showPrefixMenu, setShowPrefixMenu] = useState(false);

  // Helper to parse OCR and ASR tags out of full query string
  const parseQuery = (queryString) => {
    let mainText = queryString || "";
    let ocrText = "";
    let asrText = "";

    // Parse [OCR:"..."] or [OCR:text]
    const ocrRegex = /\s?\[OCR:((".*?")|\S+)\]/gi;
    const ocrMatch = ocrRegex.exec(mainText);
    if (ocrMatch) {
      let content = ocrMatch[1];
      if (content.startsWith('"') && content.endsWith('"')) {
        content = content.slice(1, -1);
      }
      ocrText = content;
      mainText = mainText.replace(ocrMatch[0], "");
    }

    // Parse [asr:"..."] or [asr:text]
    const asrRegex = /\s?\[asr:((".*?")|\S+)\]/gi;
    const asrMatch = asrRegex.exec(mainText);
    if (asrMatch) {
      let content = asrMatch[1];
      if (content.startsWith('"') && content.endsWith('"')) {
        content = content.slice(1, -1);
      }
      asrText = content;
      mainText = mainText.replace(asrMatch[0], "");
    }

    return { mainText: mainText.trim(), ocrText, asrText };
  };

  // Helper to rebuild query string from main, ocr, and asr inputs
  const buildQuery = (mainText, ocrText, asrText) => {
    let parts = [mainText.trim()];
    if (ocrText.trim()) {
      parts.push(`[OCR:"${ocrText.trim()}"]`);
    }
    if (asrText.trim()) {
      parts.push(`[asr:"${asrText.trim()}"]`);
    }
    return parts.filter(Boolean).join(" ");
  };

  const parsed = useMemo(() => parseQuery(q), [q]);

  const [mainQuery, setMainQuery] = useState(parsed.mainText);
  const [ocrQuery, setOcrQuery] = useState(parsed.ocrText);
  const [asrQuery, setAsrQuery] = useState(parsed.asrText);

  // Check if mainQuery has temporal delimiters \ or |
  const hasTemporal = /[\/\\|]/.test(mainQuery);

  // Extract delimiter used (\ or |)
  const temporalDelimiter = mainQuery.includes("|") ? "|" : "\\";

  // Split mainQuery into non-delimiter segment strings
  const temporalSegments = useMemo(() => {
    if (!hasTemporal) return [];
    return mainQuery.split(/[\/\\|]/);
  }, [mainQuery, hasTemporal]);

  const handleUpdateTemporalSegment = (stepIdx, newText) => {
    const currentSegments = mainQuery.split(/[\/\\|]/);
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

  // Debounced live search trigger
  useEffect(() => {
    const timer = setTimeout(() => {
      const fullQuery = buildQuery(mainQuery, ocrQuery, asrQuery);
      if (fullQuery !== q) {
        onChange(fullQuery);
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [mainQuery, ocrQuery, asrQuery, q, onChange]);

  const handleAddDirectPrefix = (prefixCode, type) => {
    if (!prefixCode) return;
    if (type === "include") {
      const existing = includeVideos ? includeVideos.trim().split(/[,;\s]+/).filter(Boolean) : [];
      if (!existing.includes(prefixCode)) {
        const nextVal = [...existing, prefixCode].join(", ");
        onIncludeVideosChange && onIncludeVideosChange(nextVal);
      }
    } else {
      const existing = excludeVideos ? excludeVideos.trim().split(/[,;\s]+/).filter(Boolean) : [];
      if (!existing.includes(prefixCode)) {
        const nextVal = [...existing, prefixCode].join(", ");
        onExcludeVideosChange && onExcludeVideosChange(nextVal);
      }
    }
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
          <div className="flex items-center gap-3">
            {isSearching && (
              <span className="text-xs text-sky-800 font-semibold animate-pulse">
                Searching...
              </span>
            )}

            {/* Temporal Mode Active Badge */}
            {hasTemporal && (
              <span className="text-[10px] bg-blue-600 text-white font-mono px-2 py-0.5 rounded-md font-bold shadow-sm">
                Temporal Mode Active
              </span>
            )}
          </div>
        </div>

        <textarea
          data-query-input="main"
          className={`w-full text-sm bg-white text-gray-900 border border-sky-400 rounded p-2 focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none font-sans transition-all ${
            hasTemporal ? "min-h-[52px] flex-1" : "h-full flex-1 min-h-[92px]"
          }`}
          rows={hasTemporal ? 2 : 3}
          placeholder="Type search text here... (Temporal syntax: '\\' for sequence, '|' for parallel/OR)"
          value={mainQuery}
          onChange={(e) => setMainQuery(e.target.value)}
          onKeyDown={handleMainQueryKeyDown}
        />

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
                  className="bg-transparent text-xs font-mono font-bold text-sky-950 focus:outline-none w-full"
                  placeholder={`Step ${stepIdx + 1} text...`}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Dedicated OCR & ASR Filters Panel */}
      <div className="w-full lg:w-56 flex flex-col gap-1.5 bg-white border border-sky-300 p-2 rounded shadow-sm">
        <label className="text-xs font-bold text-gray-800 flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-amber-500"></span>
          OCR & ASR Filters
        </label>

        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] font-bold text-blue-700">OCR Text (On-screen):</span>
          <input
            type="text"
            data-query-input="ocr"
            className="w-full bg-slate-50 border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none focus:border-blue-500 font-sans"
            placeholder="e.g. Traffic Sign, Coffee"
            value={ocrQuery}
            onChange={(e) => setOcrQuery(e.target.value)}
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
          />
        </div>
      </div>

      {/* Dedicated Include / Exclude Video Filter Panel with Header Menu */}
      <div className="w-full lg:w-56 flex flex-col gap-1.5 bg-white border border-sky-300 p-2 rounded shadow-sm relative">
        {/* Header Line with Prefix Menu Button Right Beside Video Filters */}
        <div className="flex items-center justify-between border-b border-gray-100 pb-1">
          <label className="text-xs font-bold text-gray-800 flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
            Video Filters
          </label>

          {/* Compact Prefix Menu Button */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowPrefixMenu(!showPrefixMenu)}
              className="px-2 py-0.5 text-[11px] font-bold bg-slate-100 hover:bg-slate-200 border border-gray-300 rounded text-gray-800 flex items-center gap-1 shadow-sm transition-colors"
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
                          className="w-5 h-5 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded flex items-center justify-center text-xs shadow-sm"
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
                          className="w-5 h-5 bg-red-600 hover:bg-red-700 text-white font-bold rounded flex items-center justify-center text-xs shadow-sm"
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
        </div>

        <div className="flex flex-col gap-0.5 pt-0.5">
          <span className="text-[10px] font-bold text-emerald-700">Include Video IDs:</span>
          <input
            type="text"
            className="w-full bg-slate-50 border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none focus:border-emerald-500 font-sans"
            placeholder="e.g. L26, L01_V001"
            value={includeVideos}
            onChange={(e) => onIncludeVideosChange && onIncludeVideosChange(e.target.value)}
          />
        </div>

        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] font-bold text-red-700">Exclude Video IDs:</span>
          <input
            type="text"
            className="w-full bg-slate-50 border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none focus:border-red-500 font-sans"
            placeholder="e.g. L21, L02_V005"
            value={excludeVideos}
            onChange={(e) => onExcludeVideosChange && onExcludeVideosChange(e.target.value)}
          />
        </div>
      </div>
    </div>
  );
}
