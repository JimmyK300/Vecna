import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useSelected } from "./SelectedProvider.jsx";
import { getFrameOcr, getVideoKeyframes } from "../services/search.js";

const ScoreOverlayContext = createContext(false);
const NEARBY_BATCH_SIZE = 100;

function ScoreBreakdown({ scores }) {
  if (!scores) return <span className="text-gray-400">No component scores available.</span>;
  return (
    <div className="space-y-0.5">
      <div className="flex justify-between gap-3">
        <span>Final:</span>
        <span className="font-bold text-yellow-400">{scores.final?.toFixed(4) ?? "-"}</span>
      </div>
      <div className="flex justify-between gap-3">
        <span>CLIP:</span>
        <span className="font-bold text-green-400">{scores.clip?.toFixed(4) ?? "-"}</span>
      </div>
      <div className="flex justify-between gap-3">
        <span>OCR:</span>
        <span className="font-bold text-blue-400">{scores.ocr?.toFixed(4) ?? "-"}</span>
      </div>
      <div className="flex justify-between gap-3">
        <span>ASR:</span>
        <span className="font-bold text-purple-400">{scores.asr?.toFixed(4) ?? "-"}</span>
      </div>
    </div>
  );
}

export function FrameItem({
  id,
  video_id,
  frame_id,
  thumbnail,
  score,
  scores,
  ocr,
  onPlay,
  onSearchSimilar,
  onSearchNearby,
  temporalStep,
}) {
  const { selected, addSelected, removeSelected } = useSelected();
  const showScoreOverlay = useContext(ScoreOverlayContext);
  const isSelected = selected.includes(id);

  const [showZoomModal, setShowZoomModal] = useState(false);
  const [showOcrModal, setShowOcrModal] = useState(false);
  const [ocrText, setOcrText] = useState("");
  const [loadingOcr, setLoadingOcr] = useState(false);
  const [showScores, setShowScores] = useState(false);
  const [showDetailsModal, setShowDetailsModal] = useState(false);

  const [showNearbyModal, setShowNearbyModal] = useState(false);
  const [nearbyKeyframes, setNearbyKeyframes] = useState([]);
  const [loadingNearby, setLoadingNearby] = useState(false);
  const [nearbySearchFilter, setNearbySearchFilter] = useState("");
  const [nearbyVisibleCount, setNearbyVisibleCount] = useState(NEARBY_BATCH_SIZE);

  const finalScore = scores?.final ?? score ?? 0.75;

  const getScoreBorder = (sc) => {
    if (sc >= 0.8) return "border-l-emerald-500 border-l-4";
    if (sc >= 0.5) return "border-l-amber-400 border-l-4";
    return "border-l-red-400 border-l-4";
  };

  const handleSelect = (e) => {
    e.stopPropagation();
    if (isSelected) removeSelected(id);
    else addSelected(id);
  };

  useEffect(() => {
    if (!showOcrModal) return;
    if (ocr && String(ocr).trim().length > 0) {
      setOcrText(String(ocr));
      setLoadingOcr(false);
      return;
    }

    setLoadingOcr(true);
    getFrameOcr(video_id, frame_id)
      .then((txt) => setOcrText(txt || ""))
      .catch(() => setOcrText(""))
      .finally(() => setLoadingOcr(false));
  }, [showOcrModal, video_id, frame_id, ocr]);

  useEffect(() => {
    if (!showNearbyModal || !video_id) return;
    let alive = true;
    async function fetchNearby() {
      setLoadingNearby(true);
      try {
        const res = await getVideoKeyframes(video_id);
        const list = res.keyframes || res || [];
        if (alive) setNearbyKeyframes(Array.isArray(list) ? list : []);
      } catch (err) {
        console.error("Failed to load nearby keyframes:", err);
        if (alive) setNearbyKeyframes([]);
      } finally {
        if (alive) setLoadingNearby(false);
      }
    }
    fetchNearby();
    return () => {
      alive = false;
    };
  }, [showNearbyModal, video_id]);

  const filteredNearbyKeyframes = useMemo(
    () =>
      nearbyKeyframes.filter((kf) =>
        nearbySearchFilter ? String(kf).includes(nearbySearchFilter) : true
      ),
    [nearbyKeyframes, nearbySearchFilter]
  );

  useEffect(() => {
    setNearbyVisibleCount(NEARBY_BATCH_SIZE);
  }, [showNearbyModal, nearbySearchFilter, video_id]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key !== "Escape") return;
      if (showNearbyModal) setShowNearbyModal(false);
      else if (showDetailsModal) setShowDetailsModal(false);
      else if (showOcrModal) setShowOcrModal(false);
      else if (showZoomModal) setShowZoomModal(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [showNearbyModal, showDetailsModal, showOcrModal, showZoomModal]);

  const handleNearbyScroll = (e) => {
    const node = e.currentTarget;
    if (node.scrollHeight - node.scrollTop - node.clientHeight > 800) return;
    setNearbyVisibleCount((current) =>
      Math.min(current + NEARBY_BATCH_SIZE, filteredNearbyKeyframes.length)
    );
  };

  return (
    <>
      <div
        onClick={() => onPlay?.()}
        className={`relative flex flex-col p-1 bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md transition-all cursor-pointer ${getScoreBorder(
          finalScore
        )} ${
          isSelected
            ? "ring-2 ring-blue-500 bg-blue-50/50 border-blue-300"
            : "hover:bg-gray-50/80"
        }`}
      >
        <div
          className="relative aspect-video w-full bg-black rounded-lg overflow-hidden group"
          onMouseEnter={() => setShowScores(true)}
          onMouseLeave={() => setShowScores(false)}
        >
          <img
            src={thumbnail}
            alt={`${video_id}_${frame_id}`}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
            loading="lazy"
          />

          <div className="absolute top-1 left-1 bg-black/75 backdrop-blur-sm px-1.5 py-0.5 rounded text-[10px] text-white font-mono flex gap-1 shadow-sm">
            <span className="font-semibold text-blue-300">{video_id}</span>
            <span className="text-gray-300">#</span>
            <span className="text-emerald-300">{frame_id}</span>
          </div>

          {temporalStep && (
            <div className="absolute bottom-1 left-1 bg-blue-600/90 backdrop-blur-sm text-white font-mono text-[9px] px-1.5 py-0.5 rounded font-black shadow-sm border border-blue-400 z-10">
              Step {temporalStep}
            </div>
          )}

          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setShowDetailsModal(true);
            }}
            className="absolute top-1 right-1 bg-black/80 hover:bg-black backdrop-blur-sm text-yellow-400 font-mono text-[9px] px-1.5 py-0.5 rounded-md font-extrabold shadow-sm border border-yellow-500/30"
            title="Open candidate details"
          >
            {(finalScore * 100).toFixed(0)}%
          </button>

          {(showScores || showScoreOverlay) && scores && (
            <div className="absolute bottom-0 left-0 right-0 bg-black/90 backdrop-blur-md text-white text-[10px] font-mono p-1.5 pointer-events-none border-t border-gray-800 animate-fadeIn">
              <ScoreBreakdown scores={scores} />
            </div>
          )}
        </div>

        <div
          className="flex justify-between items-center mt-1 pt-1 border-t border-gray-100 overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center gap-1 overflow-hidden shrink-0">
            <button
              onClick={onPlay}
              className="p-1 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-all shadow-sm hover:scale-105 active:scale-95 flex items-center justify-center shrink-0"
              title="Play video at frame"
            >
              <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z" />
              </svg>
            </button>

            <button
              onClick={() => (onSearchNearby ? onSearchNearby() : setShowNearbyModal(true))}
              className="p-1 bg-indigo-50 hover:bg-indigo-600 hover:text-white text-indigo-700 rounded-md border border-indigo-200 transition-all shadow-sm hover:scale-105 active:scale-95 flex items-center justify-center shrink-0"
              title="Explore nearby keyframes"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
              </svg>
            </button>

            <button
              onClick={() => setShowZoomModal(true)}
              className="p-1 bg-teal-50 hover:bg-teal-600 hover:text-white text-teal-700 rounded-md border border-teal-200 transition-all shadow-sm hover:scale-105 active:scale-95 flex items-center justify-center shrink-0"
              title="Zoom keyframe image"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v6m3-3H7" />
              </svg>
            </button>

            <button
              onClick={() => setShowOcrModal(true)}
              className="p-1 bg-amber-50 hover:bg-amber-600 hover:text-white text-amber-700 rounded-md border border-amber-200 transition-all shadow-sm hover:scale-105 active:scale-95 flex items-center justify-center shrink-0"
              title="Read on-screen OCR text"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </button>

            {onSearchSimilar && (
              <button
                onClick={onSearchSimilar}
                className="p-1 bg-purple-50 hover:bg-purple-600 hover:text-white text-purple-700 rounded-md border border-purple-200 transition-all shadow-sm hover:scale-105 active:scale-95 flex items-center justify-center shrink-0"
                title="Search similar keyframes"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </button>
            )}
          </div>

          <button
            onClick={handleSelect}
            className={`p-1 rounded-md transition-all shadow-sm flex items-center justify-center border shrink-0 ${
              isSelected
                ? "bg-emerald-600 text-white border-emerald-600 shadow-emerald-600/30"
                : "bg-gray-100 hover:bg-emerald-50 text-gray-700 border-gray-300 hover:border-emerald-500"
            }`}
            title={isSelected ? "Remove from staging" : "Add frame to staging"}
          >
            {isSelected ? (
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="3" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="3" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {showDetailsModal && (
        <div
          onClick={() => setShowDetailsModal(false)}
          className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 animate-fadeIn"
        >
          <div
            className="w-full max-w-md bg-slate-950 text-white border border-slate-700 rounded-xl shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800 bg-slate-900">
              <div>
                <div className="text-xs font-bold">Candidate details</div>
                <div className="text-[9px] font-mono text-slate-400">{id}</div>
              </div>
              <button
                type="button"
                onClick={() => setShowDetailsModal(false)}
                className="px-2 py-1 text-xs bg-slate-800 hover:bg-red-600 rounded"
              >
                ✕
              </button>
            </div>
            <div className="p-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[11px] font-mono">
              <span className="text-slate-500">Video</span><span>{video_id}</span>
              <span className="text-slate-500">Frame</span><span>{frame_id}</span>
              <span className="text-slate-500">Temporal</span><span>{temporalStep || "single frame"}</span>
              <span className="text-slate-500">OCR</span><span>{ocr && String(ocr).trim() ? "available" : "not included in result"}</span>
            </div>
            <div className="px-3 pb-3">
              <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">Ranking scores</div>
              <div className="bg-black border border-slate-800 rounded p-2 text-[10px] font-mono text-white">
                <ScoreBreakdown scores={scores} />
              </div>
              <p className="mt-2 text-[9px] leading-tight text-slate-500">
                This panel is the secondary extension point for future evidence/provenance fields when those APIs are accepted. No unavailable fields are inferred here.
              </p>
            </div>
          </div>
        </div>
      )}

      {showZoomModal && (
        <div
          onClick={() => setShowZoomModal(false)}
          className="fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex items-center justify-center p-4 animate-fadeIn"
        >
          <div
            className="relative max-w-5xl w-full bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-4 py-2.5 bg-slate-800 flex justify-between items-center border-b border-slate-700">
              <span className="font-mono text-xs font-bold text-white">Zoomed Keyframe: {video_id} #{frame_id}</span>
              <button onClick={() => setShowZoomModal(false)} className="px-2.5 py-1 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-bold">✕</button>
            </div>
            <div className="p-2 bg-black flex items-center justify-center max-h-[85vh] overflow-hidden">
              <img src={thumbnail} alt={`${video_id}_${frame_id}_zoomed`} className="max-h-[80vh] w-auto object-contain rounded-lg shadow-lg" />
            </div>
          </div>
        </div>
      )}

      {showOcrModal && (
        <div
          onClick={() => setShowOcrModal(false)}
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 animate-fadeIn"
        >
          <div
            className="relative max-w-lg w-full bg-slate-900 text-white p-4 rounded-2xl shadow-2xl flex flex-col gap-3 border border-slate-800"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center border-b border-slate-800 pb-2.5 font-bold text-xs">
              <span className="font-mono text-amber-400">OCR Text Reader <span className="text-slate-400">({video_id} #{frame_id})</span></span>
              <button onClick={() => setShowOcrModal(false)} className="px-2.5 py-1 bg-slate-800 hover:bg-red-600 text-slate-300 hover:text-white rounded-lg text-xs font-bold">✕</button>
            </div>
            <div className="bg-slate-950 border border-slate-800 text-slate-100 rounded-xl p-3.5 max-h-64 overflow-y-auto font-mono text-xs leading-relaxed whitespace-pre-wrap select-text shadow-inner">
              {loadingOcr ? (
                <div className="flex items-center gap-2 text-slate-400 italic">
                  <div className="w-4 h-4 border-2 border-amber-500 border-t-transparent rounded-full animate-spin"></div>
                  <span>Fetching detected OCR text...</span>
                </div>
              ) : ocrText ? ocrText : (
                <span className="text-slate-500 italic">No on-screen OCR text detected for this frame.</span>
              )}
            </div>
            <div className="flex justify-between items-center pt-1 border-t border-slate-800 text-xs font-mono">
              <div className="text-slate-400 text-[11px]">
                {scores?.ocr !== undefined && <span>OCR score: <strong className="text-amber-400">{scores.ocr.toFixed(4)}</strong></span>}
              </div>
              <button
                type="button"
                onClick={() => ocrText && navigator.clipboard.writeText(ocrText)}
                disabled={!ocrText}
                className="px-4 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:bg-slate-800 disabled:text-slate-600 text-white font-bold rounded-lg text-xs"
              >
                Copy Text
              </button>
            </div>
          </div>
        </div>
      )}

      {showNearbyModal && (
        <div
          onClick={() => setShowNearbyModal(false)}
          className="fixed inset-0 z-50 bg-black flex flex-col text-white animate-fadeIn"
        >
          <div className="flex flex-col h-full w-full bg-slate-950 overflow-hidden" onClick={(e) => e.stopPropagation()}>
            <div className="px-3 py-2 bg-slate-900 border-b border-slate-800 flex justify-between items-center shrink-0 gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <span className="font-bold text-xs text-white uppercase tracking-wide">Nearby Keyframes</span>
                <span className="text-xs text-blue-400 font-mono font-bold bg-blue-950 px-2 py-0.5 rounded border border-blue-800 truncate">Video: {video_id}</span>
                <span className="text-xs text-emerald-400 font-mono font-bold bg-emerald-950 px-2 py-0.5 rounded border border-emerald-800 shrink-0">Target: #{frame_id}</span>
                <span className="text-[10px] text-gray-400 font-mono shrink-0">
                  showing {Math.min(nearbyVisibleCount, filteredNearbyKeyframes.length)}/{filteredNearbyKeyframes.length}
                </span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <input
                  type="text"
                  placeholder="Jump/filter frame ID…"
                  value={nearbySearchFilter}
                  onChange={(e) => setNearbySearchFilter(e.target.value)}
                  className="bg-slate-900 border border-slate-700 text-xs px-2 py-0.5 rounded text-white font-mono focus:outline-none focus:border-blue-500 w-40"
                />
                <button onClick={() => setShowNearbyModal(false)} className="px-2.5 py-0.5 bg-red-600 hover:bg-red-700 text-white rounded text-xs font-bold">Close (Esc ✕)</button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-1 bg-black" onScroll={handleNearbyScroll}>
              {loadingNearby ? (
                <div className="w-full h-full flex flex-col items-center justify-center gap-2 text-gray-400 font-mono text-sm py-20">
                  <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
                  <span>Loading keyframe index for {video_id}...</span>
                </div>
              ) : filteredNearbyKeyframes.length === 0 ? (
                <div className="w-full text-center py-20 text-gray-400 font-mono text-sm">No matching keyframes.</div>
              ) : (
                <>
                  <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-9 xl:grid-cols-10 gap-1">
                    {filteredNearbyKeyframes.slice(0, nearbyVisibleCount).map((kf) => {
                      const kfId = `${video_id}#${kf}`;
                      const isCurrentTarget = String(kf) === String(frame_id);
                      const isSelectedFrame = selected.includes(kfId);
                      return (
                        <div
                          key={kf}
                          id={`nearby-kf-${kf}`}
                          onClick={() => {
                            if (isSelectedFrame) removeSelected(kfId);
                            else addSelected(kfId);
                          }}
                          style={{ contentVisibility: "auto", containIntrinsicSize: "100px" }}
                          className={`relative aspect-video w-full bg-black rounded overflow-hidden cursor-pointer group hover:scale-[1.02] transition-transform ${
                            isSelectedFrame
                              ? "ring-4 ring-emerald-500 z-10"
                              : isCurrentTarget
                              ? "ring-2 ring-blue-400"
                              : "hover:ring-2 hover:ring-emerald-400/60"
                          }`}
                        >
                          <img
                            src={`http://127.0.0.1:6900/api/files/${video_id}/${kf}`}
                            alt={kf}
                            loading="lazy"
                            className="w-full h-full object-cover"
                          />
                          {isSelectedFrame && <div className="absolute top-1 left-1 bg-emerald-600 text-white font-extrabold text-xs w-5 h-5 rounded-full flex items-center justify-center shadow-lg border border-white/50">✓</div>}
                          {isCurrentTarget && <div className="absolute top-0.5 right-0.5 bg-blue-600 text-white font-mono text-[8px] px-1 rounded font-black shadow-sm uppercase">TARGET</div>}
                          <div className="absolute bottom-0 left-0 bg-black/70 text-white text-[8px] font-mono px-1">#{kf}</div>
                        </div>
                      );
                    })}
                  </div>
                  {nearbyVisibleCount < filteredNearbyKeyframes.length && (
                    <div className="text-center text-[10px] font-mono text-gray-500 py-3">Scroll to progressively mount more keyframes…</div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export function FrameContainer({ children }) {
  const [showScoreOverlay, setShowScoreOverlay] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e) => {
      const activeEl = document.activeElement;
      const isInput = activeEl && ["INPUT", "TEXTAREA", "SELECT"].includes(activeEl.tagName);
      if (isInput) return;
      if (e.altKey && e.key.toLowerCase() === "s") {
        e.preventDefault();
        setShowScoreOverlay((value) => !value);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <ScoreOverlayContext.Provider value={showScoreOverlay}>
      <div className="flex justify-end mb-1 sticky top-0 z-10 pointer-events-none">
        <button
          type="button"
          onClick={() => setShowScoreOverlay((value) => !value)}
          className={`pointer-events-auto px-2 py-1 rounded border text-[9px] font-mono font-bold shadow-sm ${
            showScoreOverlay
              ? "bg-slate-900 text-white border-slate-700"
              : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
          }`}
          title="Toggle component score details across the grid (Alt+S)"
        >
          Scores {showScoreOverlay ? "ON" : "OFF"} · Alt+S
        </button>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-1">
        {children}
      </div>
    </ScoreOverlayContext.Provider>
  );
}
