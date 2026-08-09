import React, { useEffect, useMemo, useState } from "react";
import VideoScopeSelector from "./VideoScopeSelector.jsx";

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
  onVideoScopeChange,
  isSearching = false,
}) {
  const parseQuery = (queryString) => {
    let mainText = queryString || "";
    let ocrText = "";
    let asrText = "";

    const ocrRegex = /\s?\[OCR:((".*?")|\S+)\]/gi;
    const ocrMatch = ocrRegex.exec(mainText);
    if (ocrMatch) {
      let content = ocrMatch[1];
      if (content.startsWith('"') && content.endsWith('"')) content = content.slice(1, -1);
      ocrText = content;
      mainText = mainText.replace(ocrMatch[0], "");
    }

    const asrRegex = /\s?\[asr:((".*?")|\S+)\]/gi;
    const asrMatch = asrRegex.exec(mainText);
    if (asrMatch) {
      let content = asrMatch[1];
      if (content.startsWith('"') && content.endsWith('"')) content = content.slice(1, -1);
      asrText = content;
      mainText = mainText.replace(asrMatch[0], "");
    }

    return { mainText: mainText.trim(), ocrText, asrText };
  };

  const buildQuery = (mainText, ocrText, asrText) => {
    const parts = [mainText.trim()];
    if (ocrText.trim()) parts.push(`[OCR:"${ocrText.trim()}"]`);
    if (asrText.trim()) parts.push(`[asr:"${asrText.trim()}"]`);
    return parts.filter(Boolean).join(" ");
  };

  const parsed = useMemo(() => parseQuery(q), [q]);
  const [mainQuery, setMainQuery] = useState(parsed.mainText);
  const [ocrQuery, setOcrQuery] = useState(parsed.ocrText);
  const [asrQuery, setAsrQuery] = useState(parsed.asrText);
  const [manualTemporalMode, setManualTemporalMode] = useState(parsed.mainText.includes(";"));

  const grammarTemporalMode = mainQuery.includes(";");
  const hasTemporal = manualTemporalMode || grammarTemporalMode;

  const temporalSegments = useMemo(() => {
    if (!hasTemporal) return [];
    const segments = mainQuery.split(";");
    return segments.length === 1 ? [segments[0], ""] : segments;
  }, [mainQuery, hasTemporal]);

  const setTemporalSegments = (segments) => setMainQuery(segments.join(";"));

  const handleUpdateTemporalSegment = (stepIdx, newText) => {
    const currentSegments = [...temporalSegments];
    currentSegments[stepIdx] = newText;
    setTemporalSegments(currentSegments);
  };

  const handleAddTemporalSegment = () => {
    setManualTemporalMode(true);
    setTemporalSegments([...temporalSegments, ""]);
  };

  const handleRemoveTemporalSegment = (stepIdx) => {
    const nextSegments = temporalSegments.filter((_, idx) => idx !== stepIdx);
    if (nextSegments.length <= 1) {
      setMainQuery((nextSegments[0] || "").trim());
      setManualTemporalMode(false);
      return;
    }
    setTemporalSegments(nextSegments);
  };

  const handleToggleTemporalMode = () => {
    if (hasTemporal) {
      setMainQuery(temporalSegments.map((segment) => segment.trim()).filter(Boolean).join(" "));
      setManualTemporalMode(false);
      return;
    }
    setManualTemporalMode(true);
    setMainQuery(`${mainQuery};`);
  };

  useEffect(() => {
    const p = parseQuery(q);
    setMainQuery(p.mainText);
    setOcrQuery(p.ocrText);
    setAsrQuery(p.asrText);
    setManualTemporalMode(p.mainText.includes(";"));
  }, [q]);

  useEffect(() => {
    const timer = setTimeout(() => {
      const fullQuery = buildQuery(mainQuery, ocrQuery, asrQuery);
      if (fullQuery !== q) onChange(fullQuery);
    }, 400);
    return () => clearTimeout(timer);
  }, [mainQuery, ocrQuery, asrQuery, q, onChange]);

  const handleMainQueryKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onChange(buildQuery(mainQuery, ocrQuery, asrQuery));
    }
  };

  return (
    <div className="w-full flex flex-col lg:flex-row gap-2 bg-sky-200 border border-sky-300 p-2 rounded-lg shadow-sm mb-2">
      <div className="flex-1 flex flex-col gap-1.5 h-full">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-3">
            {isSearching && <span className="text-xs text-sky-800 font-semibold animate-pulse">Searching...</span>}
            {hasTemporal && (
              <span className="text-[10px] bg-blue-600 text-white font-mono px-2 py-0.5 rounded-md font-bold shadow-sm">
                Temporal Mode Active
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={handleToggleTemporalMode}
            className={`px-2 py-1 rounded-md border text-[10px] font-bold font-mono transition-colors ${
              hasTemporal
                ? "bg-blue-700 border-blue-800 text-white hover:bg-blue-800"
                : "bg-white border-sky-400 text-sky-800 hover:bg-sky-50"
            }`}
            title={hasTemporal ? "Exit temporal mode" : "Enter temporal mode"}
          >
            {hasTemporal ? "Exit Temporal" : "+ Temporal"}
          </button>
        </div>

        <textarea
          data-query-input="main"
          className={`w-full text-sm bg-white text-gray-900 border border-sky-400 rounded p-2 focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none font-sans transition-all ${
            hasTemporal ? "min-h-[52px] flex-1" : "h-full flex-1 min-h-[92px]"
          }`}
          rows={hasTemporal ? 2 : 3}
          placeholder="Type search text here... Use ';' between temporal steps, or press + Temporal."
          value={mainQuery}
          onChange={(e) => setMainQuery(e.target.value)}
          onKeyDown={handleMainQueryKeyDown}
        />

        {hasTemporal && (
          <div className="flex flex-col gap-1.5 pt-1 border-t border-sky-300 w-full animate-fadeIn">
            <div className="flex items-center justify-between gap-2 text-[9px] font-mono text-sky-800">
              <span>Steps are sent as the backend-supported <strong>;</strong> sequence grammar.</span>
              <button type="button" onClick={handleAddTemporalSegment} className="px-2 py-0.5 bg-white hover:bg-sky-50 border border-sky-400 rounded font-bold shrink-0">
                + Step
              </button>
            </div>
            {temporalSegments.map((segmentText, stepIdx) => (
              <div key={stepIdx} className="flex items-center bg-white border border-sky-400 px-2 py-1 rounded-lg text-xs font-semibold text-sky-950 font-mono shadow-sm focus-within:ring-1 focus-within:ring-blue-500 w-full">
                <span className="text-[10px] text-sky-600 font-bold mr-1.5 shrink-0 select-none">#{stepIdx + 1}</span>
                <input
                  type="text"
                  value={segmentText}
                  onChange={(e) => handleUpdateTemporalSegment(stepIdx, e.target.value)}
                  className="bg-transparent text-xs font-mono font-bold text-sky-950 focus:outline-none w-full"
                  placeholder={`Step ${stepIdx + 1} text...`}
                />
                {temporalSegments.length > 1 && (
                  <button type="button" onClick={() => handleRemoveTemporalSegment(stepIdx)} className="ml-1 px-1 text-red-500 hover:text-red-700 font-bold" title={`Remove step ${stepIdx + 1}`}>
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="w-full lg:w-56 flex flex-col gap-1.5 bg-white border border-sky-300 p-2 rounded shadow-sm">
        <label className="text-xs font-bold text-gray-800 flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-amber-500"></span>
          OCR & ASR Filters
        </label>
        <p className="text-[9px] leading-tight text-gray-500 font-mono">
          Empty field = use the main query when that modality has non-zero weight. Weight 0 = disabled.
        </p>
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] font-bold text-blue-700">OCR Text (On-screen):</span>
          <input
            type="text"
            data-query-input="ocr"
            className="w-full bg-slate-50 border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none focus:border-blue-500 font-sans"
            placeholder="Empty → main query"
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
            placeholder="Empty → main query if enabled"
            value={asrQuery}
            onChange={(e) => setAsrQuery(e.target.value)}
          />
        </div>
      </div>

      <VideoScopeSelector
        includeVideos={includeVideos}
        excludeVideos={excludeVideos}
        onScopeChange={onVideoScopeChange}
        onIncludeVideosChange={onIncludeVideosChange}
        onExcludeVideosChange={onExcludeVideosChange}
        groups={VIDEO_PREFIX_OPTIONS}
      />
    </div>
  );
}
