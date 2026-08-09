import React, { useState, useEffect } from "react";
import { useSelected } from "./SelectedProvider.jsx";
import { getVideoKeyframes, getFrameOcr } from "../services/search.js";

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
  const isSelected = selected.includes(id);

  // Zoom Modal State
  const [showZoomModal, setShowZoomModal] = useState(false);

  // OCR Modal State
  const [showOcrModal, setShowOcrModal] = useState(false);
  const [ocrText, setOcrText] = useState("");
  const [loadingOcr, setLoadingOcr] = useState(false);

  const [showScores, setShowScores] = useState(false);

  // Fullscreen Nearby Keyframes Explorer Modal state
  const [showNearbyModal, setShowNearbyModal] = useState(false);
  const [nearbyKeyframes, setNearbyKeyframes] = useState([]);
  const [loadingNearby, setLoadingNearby] = useState(false);
  const [nearbySearchFilter, setNearbySearchFilter] = useState("");

  const finalScore = scores?.final ?? score ?? 0.75;

  const getConfidenceBorder = (sc) => {
    if (sc >= 0.8) return "border-l-emerald-500 border-l-4";
    if (sc >= 0.5) return "border-l-amber-400 border-l-4";
    return "border-l-red-400 border-l-4";
  };

  const handleSelect = (e) => {
    e.stopPropagation();
    if (isSelected) {
      removeSelected(id);
    } else {
      addSelected(id);
    }
  };

  // Load OCR text when OCR modal is opened
  useEffect(() => {
    if (showOcrModal) {
      if (ocr && String(ocr).trim().length > 0) {
        setOcrText(String(ocr));
        setLoadingOcr(false);
      } else {
        setLoadingOcr(true);
        getFrameOcr(video_id, frame_id)
          .then((txt) => {
            setOcrText(txt || "");
          })
          .catch(() => {
            setOcrText("");
          })
          .finally(() => {
            setLoadingOcr(false);
          });
      }
    }
  }, [showOcrModal, video_id, frame_id, ocr]);

  // Load nearby keyframes for video_id when modal is opened
  useEffect(() => {
    if (showNearbyModal && video_id) {
      async function fetchNearby() {
        setLoadingNearby(true);
        try {
          const res = await getVideoKeyframes(video_id);
          const list = res.keyframes || res || [];
          setNearbyKeyframes(Array.isArray(list) ? list : []);
        } catch (err) {
          console.error("Failed to load nearby keyframes:", err);
          setNearbyKeyframes([]);
        } finally {
          setLoadingNearby(false);
        }
      }
      fetchNearby();
    }
  }, [showNearbyModal, video_id]);

  // Escape key listener to close modals
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        if (showNearbyModal) setShowNearbyModal(false);
        if (showOcrModal) setShowOcrModal(false);
        if (showZoomModal) setShowZoomModal(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [showNearbyModal, showOcrModal, showZoomModal]);

  return (
    <>
      <div
        onClick={() => onPlay?.()}
        className={`relative flex flex-col p-1 bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md transition-all cursor-pointer ${getConfidenceBorder(
          finalScore
        )} ${
          isSelected ? "ring-2 ring-blue-500 bg-blue-50/50 border-blue-300" : "hover:bg-gray-50/80"
        }`}
      >
        {/* Frame Image Thumbnail */}
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

          {/* Video ID & Frame ID Tag */}
          <div className="absolute top-1 left-1 bg-black/75 backdrop-blur-sm px-1.5 py-0.5 rounded text-[10px] text-white font-mono flex gap-1 shadow-sm">
            <span className="font-semibold text-blue-300">{video_id}</span>
            <span className="text-gray-300">#</span>
            <span className="text-emerald-300">{frame_id}</span>
          </div>

          {/* Temporal Step Badge */}
          {temporalStep && (
            <div className="absolute bottom-1 left-1 bg-blue-600/90 backdrop-blur-sm text-white font-mono text-[9px] px-1.5 py-0.5 rounded font-black shadow-sm border border-blue-400 z-10">
              Step {temporalStep}
            </div>
          )}

          {/* Score Badge */}
          <div className="absolute top-1 right-1 bg-black/80 backdrop-blur-sm text-yellow-400 font-mono text-[9px] px-1.5 py-0.5 rounded-md font-extrabold shadow-sm border border-yellow-500/30">
            {(finalScore * 100).toFixed(0)}%
          </div>

          {/* Detailed Score Popup on Hover */}
          {showScores && scores && (
            <div className="absolute bottom-0 left-0 right-0 bg-black/90 backdrop-blur-md text-white text-[10px] font-mono p-1.5 space-y-0.5 pointer-events-none border-t border-gray-800 animate-fadeIn">
              <div className="flex justify-between">
                <span>Final:</span>
                <span className="font-bold text-yellow-400">{scores.final?.toFixed(4) ?? "-"}</span>
              </div>
              <div className="flex justify-between">
                <span>CLIP:</span>
                <span className="font-bold text-green-400">{scores.clip?.toFixed(4) ?? "-"}</span>
              </div>
              <div className="flex justify-between">
                <span>OCR:</span>
                <span className="font-bold text-blue-400">{scores.ocr?.toFixed(4) ?? "-"}</span>
              </div>
              <div className="flex justify-between">
                <span>ASR:</span>
                <span className="font-bold text-purple-400">{scores.asr?.toFixed(4) ?? "-"}</span>
              </div>
            </div>
          )}
        </div>

        {/* Action Controls Toolbar (Priority: Play -> Nearby -> Zoom -> OCR -> Similar -> Add) */}
        <div
          className="flex justify-between items-center mt-1 pt-1 border-t border-gray-100 overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center gap-1 overflow-hidden shrink-0">
            {/* 1. Play Video Icon Button (1st Priority) */}
            <button
              onClick={onPlay}
              className="p-1 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-all shadow-sm hover:scale-105 active:scale-95 flex items-center justify-center shrink-0"
              title="Play video at frame"
            >
              <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z" />
              </svg>
            </button>

            {/* 2. Nearby Keyframes Icon Button (2nd Priority) */}
            <button
              onClick={() => (onSearchNearby ? onSearchNearby() : setShowNearbyModal(true))}
              className="p-1 bg-indigo-50 hover:bg-indigo-600 hover:text-white text-indigo-700 rounded-md border border-indigo-200 transition-all shadow-sm hover:scale-105 active:scale-95 flex items-center justify-center shrink-0"
              title="Explore Nearby Keyframes in Video"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
              </svg>
            </button>

            {/* 3. Zoom Frame Icon Button (3rd Priority) */}
            <button
              onClick={() => setShowZoomModal(true)}
              className="p-1 bg-teal-50 hover:bg-teal-600 hover:text-white text-teal-700 rounded-md border border-teal-200 transition-all shadow-sm hover:scale-105 active:scale-95 flex items-center justify-center shrink-0"
              title="Zoom keyframe image"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v6m3-3H7" />
              </svg>
            </button>

            {/* 4. OCR Reader Icon Button (4th Priority) */}
            <button
              onClick={() => setShowOcrModal(true)}
              className="p-1 bg-amber-50 hover:bg-amber-600 hover:text-white text-amber-700 rounded-md border border-amber-200 transition-all shadow-sm hover:scale-105 active:scale-95 flex items-center justify-center shrink-0"
              title="Read On-screen OCR Text"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </button>

            {/* 5. Search Similar Icon Button (5th Priority) */}
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

          {/* 6. Add / Selected Toggle Icon Button (6th Priority, Rightmost) */}
          <button
            onClick={handleSelect}
            className={`p-1 rounded-md transition-all shadow-sm flex items-center justify-center border shrink-0 ${
              isSelected
                ? "bg-emerald-600 text-white border-emerald-600 shadow-emerald-600/30"
                : "bg-gray-100 hover:bg-emerald-50 text-gray-700 border-gray-300 hover:border-emerald-500"
            }`}
            title={isSelected ? "Remove from payload" : "Add frame to payload"}
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
      {/* Zoom Image Modal */}
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
              <span className="font-mono text-xs font-bold text-white flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-teal-400 animate-pulse"></span>
                Zoomed Keyframe: {video_id} #{frame_id}
              </span>
              <button
                onClick={() => setShowZoomModal(false)}
                className="px-2.5 py-1 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-bold shadow-sm transition-colors"
              >
                ✕
              </button>
            </div>

            <div className="p-2 bg-black flex items-center justify-center max-h-[85vh] overflow-hidden">
              <img
                src={thumbnail}
                alt={`${video_id}_${frame_id}_zoomed`}
                className="max-h-[80vh] w-auto object-contain rounded-lg shadow-lg"
              />
            </div>
          </div>
        </div>
      )}

      {/* OCR Text Reader Modal */}
      {showOcrModal && (
        <div
          onClick={() => setShowOcrModal(false)}
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 animate-fadeIn"
        >
          <div
            className="relative max-w-lg w-full bg-slate-900 text-white p-4.5 rounded-2xl shadow-2xl flex flex-col gap-3.5 border border-slate-800"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex justify-between items-center border-b border-slate-800 pb-2.5 font-bold text-xs">
              <span className="flex items-center gap-2 font-mono">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse"></span>
                <span className="text-amber-400 font-extrabold uppercase">OCR Text Reader</span>
                <span className="text-slate-400">({video_id} #{frame_id})</span>
              </span>
              <button
                onClick={() => setShowOcrModal(false)}
                className="px-2.5 py-1 bg-slate-800 hover:bg-red-600 text-slate-300 hover:text-white rounded-lg text-xs font-bold transition-colors"
              >
                ✕
              </button>
            </div>

            {/* Modal Body: Actual OCR Text Content */}
            <div className="bg-slate-950 border border-slate-800 text-slate-100 rounded-xl p-3.5 max-h-64 overflow-y-auto font-mono text-xs leading-relaxed whitespace-pre-wrap select-text shadow-inner">
              {loadingOcr ? (
                <div className="flex items-center gap-2 text-slate-400 italic">
                  <div className="w-4 h-4 border-2 border-amber-500 border-t-transparent rounded-full animate-spin"></div>
                  <span>Fetching detected OCR text...</span>
                </div>
              ) : ocrText ? (
                ocrText
              ) : (
                <span className="text-slate-500 italic">No on-screen OCR text detected for this frame.</span>
              )}
            </div>

            {/* Modal Footer: Score Indicator & Copy Text Button */}
            <div className="flex justify-between items-center pt-1 border-t border-slate-800 text-xs font-mono">
              <div className="text-slate-400 text-[11px]">
                {scores?.ocr !== undefined && (
                  <span>OCR Match Score: <strong className="text-amber-400 font-bold">{(scores.ocr * 100).toFixed(1)}%</strong></span>
                )}
              </div>
              <button
                type="button"
                onClick={() => {
                  if (ocrText) {
                    navigator.clipboard.writeText(ocrText);
                    alert("Copied OCR text to clipboard!");
                  }
                }}
                disabled={!ocrText}
                className="px-4 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:bg-slate-800 disabled:text-slate-600 text-white font-bold rounded-lg text-xs shadow-md transition-colors flex items-center gap-1.5"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                Copy Text
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Fullscreen Nearby Keyframes Explorer Modal (True Edge-to-Edge & Super Tight Grid) */}
      {showNearbyModal && (
        <div
          onClick={() => setShowNearbyModal(false)}
          className="fixed inset-0 z-50 bg-black flex flex-col text-white animate-fadeIn"
        >
          <div
            className="flex flex-col h-full w-full bg-slate-950 overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Sleek Minimal Header */}
            <div className="px-3 py-2 bg-slate-900 border-b border-slate-800 flex justify-between items-center shrink-0">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
                <span className="font-bold text-xs text-white uppercase tracking-wide">Nearby Keyframes</span>
                <span className="text-xs text-blue-400 font-mono font-bold bg-blue-950 px-2 py-0.5 rounded border border-blue-800">
                  Video: {video_id}
                </span>
                <span className="text-xs text-emerald-400 font-mono font-bold bg-emerald-950 px-2 py-0.5 rounded border border-emerald-800">
                  Target: #{frame_id}
                </span>
                <span className="text-xs text-gray-400 font-mono">
                  ({nearbyKeyframes.length} frames)
                </span>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="text"
                  placeholder="Filter frame ID..."
                  value={nearbySearchFilter}
                  onChange={(e) => setNearbySearchFilter(e.target.value)}
                  className="bg-slate-900 border border-slate-700 text-xs px-2 py-0.5 rounded text-white font-mono focus:outline-none focus:border-blue-500 w-36"
                />
                <button
                  onClick={() => setShowNearbyModal(false)}
                  className="px-2.5 py-0.5 bg-red-600 hover:bg-red-700 text-white rounded text-xs font-bold shadow-sm transition-colors"
                >
                  Close (Esc ✕)
                </button>
              </div>
            </div>

            {/* Fullscreen Edge-to-Edge Grid (Tight gap-1 spacing, 10 cols) */}
            <div className="flex-1 overflow-y-auto p-1 bg-black">
              {loadingNearby ? (
                <div className="w-full h-full flex flex-col items-center justify-center gap-2 text-gray-400 font-mono text-sm py-20">
                  <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
                  <span>Loading keyframes for {video_id}...</span>
                </div>
              ) : nearbyKeyframes.length === 0 ? (
                <div className="w-full text-center py-20 text-gray-400 font-mono text-sm">
                  No keyframes found for video: {video_id}
                </div>
              ) : (
                <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-9 xl:grid-cols-10 gap-1">
                  {nearbyKeyframes
                    .filter((kf) => (nearbySearchFilter ? String(kf).includes(nearbySearchFilter) : true))
                    .map((kf) => {
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
                          className={`relative aspect-video w-full bg-black rounded overflow-hidden cursor-pointer group hover:scale-[1.03] transition-transform ${
                            isSelectedFrame
                              ? "ring-4 ring-emerald-500 z-10"
                              : isCurrentTarget
                              ? "ring-2 ring-blue-400"
                              : "hover:ring-2 hover:ring-emerald-400/60"
                          }`}
                        >
                          {/* Thumbnail Image */}
                          <img
                            src={`http://127.0.0.1:6900/api/files/${video_id}/${kf}`}
                            alt={kf}
                            loading="lazy"
                            className="w-full h-full object-cover"
                          />

                          {/* Selected Checkmark Badge */}
                          {isSelectedFrame && (
                            <div className="absolute top-1 left-1 bg-emerald-600 text-white font-extrabold text-xs w-5 h-5 rounded-full flex items-center justify-center shadow-lg border border-white/50">
                              ✓
                            </div>
                          )}

                          {/* Current Target Indicator Badge */}
                          {isCurrentTarget && (
                            <div className="absolute top-0.5 right-0.5 bg-blue-600 text-white font-mono text-[8px] px-1 py-0.2 rounded font-black shadow-sm uppercase">
                              TARGET
                            </div>
                          )}
                        </div>
                      );
                    })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export function FrameContainer({ children }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-1">
      {children}
    </div>
  );
}