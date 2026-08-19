import React, { useState, useEffect } from "react";
import { useSelected } from "./SelectedProvider.jsx";
import { getVideoKeyframes, getFrameOcr, getMapKeyframesAround, pinpointMoment } from "../services/search.js";

export function FrameItem({
  id,
  video_id,
  frame_id,
  thumbnail,
  keyframe,
  score,
  scores,
  ocr,
  onPlay,
  onSearchSimilar,
  onSearchNearby,
  temporalStep,
  totalScore,
  onAddIncludeVideo,
  onAddExcludeVideo,
  currentQuery,
}) {
  const { selected, addSelected, removeSelected } = useSelected();
  const isSelected = selected.includes(id);

  // Zoom Modal State
  const [showZoomModal, setShowZoomModal] = useState(false);

  // Construct High-Resolution Keyframe URL from keyframes endpoint
  const keyframeUrl =
    keyframe ||
    (thumbnail
      ? thumbnail.replace("/api/files/", "/api/keyframes/")
      : `http://127.0.0.1:6900/api/keyframes/${video_id}/${frame_id}`);

  const [zoomImgSrc, setZoomImgSrc] = useState(keyframeUrl);

  useEffect(() => {
    setZoomImgSrc(keyframeUrl);
  }, [keyframeUrl]);

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

  // Map Keyframes Modal State
  const [showMapModal, setShowMapModal] = useState(false);
  const [mapAroundData, setMapAroundData] = useState(null);
  const [loadingMap, setLoadingMap] = useState(false);

  // Pinpoint First Occurrence Modal State
  const extractEventQuery = (queryText, step) => {
    if (!queryText) return "";
    let cleanQ = String(queryText).replace(/\[(?:video|!video|exclude_video):[^\]]+\]/gi, "").trim();
    const steps = cleanQ.split(/[\\/]/).map((s) => s.trim()).filter(Boolean);
    if (steps.length > 1 && step) {
      const match = String(step).match(/(\d+)\s*\/\s*(\d+)/);
      if (match) {
        const idx = parseInt(match[1], 10) - 1;
        if (idx >= 0 && idx < steps.length) {
          return steps[idx];
        }
      }
    }
    return steps.length > 0 ? steps[0] : cleanQ;
  };

  const [showPinpointModal, setShowPinpointModal] = useState(false);
  const [loadingPinpoint, setLoadingPinpoint] = useState(false);
  const [pinpointData, setPinpointData] = useState(null);
  const [pinpointError, setPinpointError] = useState(null);
  const [pinpointQueryInput, setPinpointQueryInput] = useState(extractEventQuery(currentQuery || "", temporalStep));

  useEffect(() => {
    if (currentQuery) {
      setPinpointQueryInput(extractEventQuery(currentQuery, temporalStep));
    }
  }, [currentQuery, temporalStep]);

  const handleOpenPinpoint = async () => {
    setShowPinpointModal(true);
    const queryToUse = pinpointQueryInput || extractEventQuery(currentQuery || "", temporalStep);
    if (!pinpointData) {
      await handleExecutePinpoint(queryToUse);
    }
  };

  const handleExecutePinpoint = async (queryText) => {
    setLoadingPinpoint(true);
    setPinpointError(null);
    try {
      const res = await pinpointMoment(video_id, frame_id, queryText || "", 30.0, 5.0);
      if (res && res.status === "success") {
        setPinpointData(res);
      } else {
        setPinpointError(res?.message || "Không thể định vị được khoảnh khắc.");
      }
    } catch (err) {
      setPinpointError(err?.response?.data?.message || err.message || "Lỗi kết nối khi gửi yêu cầu Pinpoint.");
    } finally {
      setLoadingPinpoint(false);
    }
  };

  const handleSelect = async (e) => {
    if (e && e.stopPropagation) e.stopPropagation();
    if (isSelected) {
      removeSelected(id);
    } else {
      setLoadingMap(true);
      try {
        const res = await getMapKeyframesAround(video_id, frame_id);
        if (res && res.available) {
          setMapAroundData(res);
          setShowMapModal(true);
        } else {
          // Safety Fallback if map-keyframes is unavailable
          addSelected(id);
        }
      } catch (err) {
        addSelected(id);
      } finally {
        setLoadingMap(false);
      }
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

  // Escape key listener to close modals (including Keyframe Map / Add Payload modal)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        if (showMapModal) setShowMapModal(false);
        if (showNearbyModal) setShowNearbyModal(false);
        if (showOcrModal) setShowOcrModal(false);
        if (showZoomModal) setShowZoomModal(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [showMapModal, showNearbyModal, showOcrModal, showZoomModal]);

  const handleCardClick = (e) => {
    if (isSelected) {
      removeSelected(id);
    } else {
      addSelected(id);
    }
  };

  return (
    <>
      <div
        onClick={handleCardClick}
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

          {/* Temporal Event Badge (Hidden when hover score popup is shown) */}
          {temporalStep && !showScores && (
            <div className="absolute bottom-1 left-1 bg-blue-600/90 backdrop-blur-sm text-white font-mono text-[9px] px-1.5 py-0.5 rounded font-black shadow-sm border border-blue-400 z-10">
              Event {temporalStep}
            </div>
          )}

          {/* Quick Include (+) / Exclude (-) Video Filter Buttons (Visible on hover) */}
          <div className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200 flex items-center gap-1 z-20">
            {onAddIncludeVideo && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onAddIncludeVideo(video_id);
                }}
                className="w-6 h-6 bg-emerald-600 hover:bg-emerald-700 active:scale-95 text-white font-bold rounded flex items-center justify-center text-xs shadow-md border border-emerald-400 cursor-pointer transition-all"
                title={`Include video ${video_id}`}
              >
                +
              </button>
            )}
            {onAddExcludeVideo && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onAddExcludeVideo(video_id);
                }}
                className="w-6 h-6 bg-red-600 hover:bg-red-700 active:scale-95 text-white font-bold rounded flex items-center justify-center text-xs shadow-md border border-red-400 cursor-pointer transition-all"
                title={`Exclude video ${video_id}`}
              >
                -
              </button>
            )}
          </div>

          {/* Detailed Score Popup on Hover */}
          {showScores && scores && (
            <div className="absolute bottom-0 left-0 right-0 bg-black/90 backdrop-blur-md text-white text-[10px] font-mono p-1.5 space-y-0.5 pointer-events-none border-t border-gray-800 animate-fadeIn z-20">
              {totalScore !== null && totalScore !== undefined && (
                <div className="flex justify-between border-b border-gray-700 pb-0.5 mb-0.5">
                  <span className="text-amber-300 font-bold">Seq Total:</span>
                  <span className="font-extrabold text-amber-300">{totalScore?.toFixed(4) ?? "-"}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span>{temporalStep ? "Step Score:" : "Final:"}</span>
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

            {/* 6. Pinpoint First Occurrence / Action Boundary Button */}
            <button
              onClick={handleOpenPinpoint}
              className="p-1 bg-rose-50 hover:bg-rose-600 hover:text-white text-rose-700 rounded-md border border-rose-200 transition-all shadow-sm hover:scale-105 active:scale-95 flex items-center justify-center shrink-0"
              title="🎯 Pinpoint First Occurrence (Exact Frame)"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="9" />
                <circle cx="12" cy="12" r="3" fill="currentColor" />
                <path strokeLinecap="round" d="M12 2v3m0 14v3M2 12h3m14 0h3" />
              </svg>
            </button>
          </div>

          {/* 7. Add / Selected Toggle Icon Button (Rightmost) */}
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
          className="fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex items-center justify-center p-2 sm:p-4 md:p-6 animate-fadeIn"
        >
          <div
            className="relative max-w-[94vw] max-h-[94vh] w-full bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header & Toolbar */}
            <div className="px-4 py-2.5 bg-slate-900 flex justify-between items-center border-b border-slate-800 shrink-0 flex-wrap gap-2">
              <div className="flex items-center gap-2 font-mono text-xs font-bold text-white">
                <span className="w-2.5 h-2.5 rounded-full bg-teal-400 animate-pulse"></span>
                <span>Zoomed Keyframe:</span>
                <span className="text-teal-300 font-extrabold">{video_id}</span>
                <span className="text-emerald-400 font-extrabold">#{frame_id}</span>
                <span className="hidden md:inline-flex items-center px-2 py-0.5 rounded text-[10px] bg-teal-950 text-teal-300 border border-teal-800 uppercase tracking-wider font-bold">
                  HD Keyframe
                </span>
              </div>

              <div className="flex items-center gap-2">
                {/* Copy Frame ID Button */}
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(`${video_id}#${frame_id}`);
                    alert(`Copied frame ID: ${video_id}#${frame_id}`);
                  }}
                  className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white rounded-lg text-xs font-bold shadow-sm transition-all border border-slate-700 flex items-center gap-1.5"
                  title="Copy frame string to clipboard"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                  <span>Copy ID</span>
                </button>

                {/* Open HD Image in New Tab */}
                <a
                  href={zoomImgSrc}
                  target="_blank"
                  rel="noreferrer"
                  className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-teal-300 hover:text-teal-200 rounded-lg text-xs font-bold shadow-sm transition-all border border-slate-700 flex items-center gap-1.5"
                  title="Open full resolution image in new tab"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                  <span>Open HD</span>
                </a>

                {/* Add / Remove Payload Toggle */}
                <button
                  type="button"
                  onClick={handleSelect}
                  className={`px-2.5 py-1 rounded-lg text-xs font-bold shadow-sm transition-all flex items-center gap-1.5 border ${
                    isSelected
                      ? "bg-emerald-600 text-white border-emerald-500 shadow-emerald-600/30"
                      : "bg-slate-800 hover:bg-emerald-950 text-slate-200 hover:text-emerald-300 border-slate-700"
                  }`}
                  title={isSelected ? "Remove from payload" : "Add frame to payload"}
                >
                  {isSelected ? "✓ Selected" : "+ Add Payload"}
                </button>

                {/* Close Modal Button */}
                <button
                  onClick={() => setShowZoomModal(false)}
                  className="px-2.5 py-1 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-bold shadow-sm transition-colors flex items-center gap-1"
                >
                  ✕ Close
                </button>
              </div>
            </div>

            {/* Modal Body: Large High-Res Image Display */}
            <div className="p-2 sm:p-4 bg-black/95 flex-1 flex items-center justify-center min-h-[50vh] max-h-[82vh] overflow-hidden relative group">
              <img
                src={zoomImgSrc}
                alt={`${video_id}_${frame_id}_zoomed`}
                className="max-h-[80vh] max-w-full w-auto h-auto object-contain rounded-lg shadow-2xl transition-all duration-300"
                onError={() => {
                  if (zoomImgSrc !== thumbnail && thumbnail) {
                    setZoomImgSrc(thumbnail);
                  }
                }}
              />
            </div>

            {/* Modal Footer: Keyframe Path & Score Badges */}
            <div className="px-4 py-2 bg-slate-900 border-t border-slate-800 flex justify-between items-center text-xs font-mono text-slate-400 shrink-0 flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <span className="text-slate-500">Source:</span>
                <span className="text-slate-300 bg-slate-800 px-2 py-0.5 rounded border border-slate-700 text-[11px]">
                  /keyframes/{video_id}/{frame_id}.jpg
                </span>
              </div>
              {scores && (
                <div className="flex items-center gap-2 text-[11px]">
                  {scores.final !== undefined && (
                    <span>Score: <strong className="text-amber-400">{scores.final?.toFixed(4)}</strong></span>
                  )}
                  {scores.clip !== undefined && (
                    <span>CLIP: <strong className="text-emerald-400">{scores.clip?.toFixed(4)}</strong></span>
                  )}
                  {scores.ocr !== undefined && (
                    <span>OCR: <strong className="text-blue-400">{scores.ocr?.toFixed(4)}</strong></span>
                  )}
                  {scores.asr !== undefined && (
                    <span>ASR: <strong className="text-purple-400">{scores.asr?.toFixed(4)}</strong></span>
                  )}
                </div>
              )}
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

      {/* Map Keyframes Selector Modal (Option 2) */}
      {showMapModal && mapAroundData && (
        <div
          onClick={() => setShowMapModal(false)}
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-3 sm:p-5 animate-fadeIn"
        >
          <div
            className="bg-white border border-gray-200 rounded-2xl p-6 max-w-5xl w-full shadow-2xl space-y-4 text-gray-900 font-sans"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex justify-between items-center border-b border-gray-200 pb-3">
              <div>
                <h3 className="font-bold text-gray-900 text-xl flex items-center gap-2">
                  <span className="w-3.5 h-3.5 rounded-full bg-emerald-500 animate-pulse"></span>
                  <span>Keyframe Selector</span>
                  <span className="text-blue-600 font-extrabold font-mono">{video_id}</span>
                </h3>
                <p className="text-xs sm:text-sm text-gray-500 font-mono mt-0.5">
                  Search frame: <span className="text-blue-700 font-bold">#{frame_id}</span>
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowMapModal(false)}
                className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 hover:text-gray-900 rounded-xl text-xs sm:text-sm font-bold transition-colors border border-gray-300 shadow-sm"
              >
                ✕ Close
              </button>
            </div>

            <p className="text-xs sm:text-sm text-gray-600">
              {mapAroundData.is_exact_match
                ? "This frame is an official Keyframe. Would you like to add it to your submission payload?"
                : "This search frame is an intermediate frame. Select one of the keyframe options to add to payload:"}
            </p>

            {mapAroundData.is_exact_match ? (
              /* Single Card Mode when frame is an exact Keyframe */
              <div className="flex justify-center py-2">
                {mapAroundData.curr && (
                  <div className="bg-blue-50/30 border-2 border-blue-500 rounded-2xl p-4.5 flex flex-col items-center space-y-3.5 shadow-xl shadow-blue-500/10 max-w-lg w-full group">
                    <div className="text-xs sm:text-sm font-extrabold text-blue-800 bg-blue-100 px-3.5 py-1.5 rounded-full border border-blue-300 w-full text-center">
                      ✓ Official Keyframe (n={mapAroundData.curr.n})
                    </div>
                    {mapAroundData.curr.is_fallback_image && (
                      <div className="text-xs text-amber-800 bg-amber-50 px-3 py-1 rounded-lg border border-amber-200 font-mono text-center w-full font-semibold">
                        ⚠️ Keyframe #{mapAroundData.curr.frame_idx} missing — Displaying closest frame #{mapAroundData.curr.display_frame_idx}
                      </div>
                    )}
                    <div className="w-full aspect-video rounded-xl overflow-hidden bg-gray-100 relative border border-blue-300 shadow-inner">
                      <img
                        src={`http://127.0.0.1:6900/api/keyframes/${video_id}/${mapAroundData.curr.display_frame_idx || mapAroundData.curr.frame_idx}`}
                        onError={(e) => {
                          e.target.onerror = null;
                          e.target.src = `http://127.0.0.1:6900/api/files/${video_id}/${mapAroundData.curr.display_frame_idx || mapAroundData.curr.frame_idx}`;
                        }}
                        alt={`n=${mapAroundData.curr.n}`}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                      />
                    </div>
                    <div className="text-xs sm:text-sm font-mono text-blue-950 text-center font-bold">
                      Frame: #{mapAroundData.curr.frame_idx} {mapAroundData.curr.is_fallback_image ? `(Shown: #${mapAroundData.curr.display_frame_idx})` : ""} | {mapAroundData.curr.pts_time}s
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        addSelected(`${video_id}#${mapAroundData.curr.frame_idx}`);
                        setShowMapModal(false);
                      }}
                      className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-extrabold text-xs sm:text-sm rounded-xl transition-all shadow-md shadow-blue-600/20 flex items-center justify-center gap-1.5 active:scale-95"
                    >
                      + Add Keyframe (n={mapAroundData.curr.n})
                    </button>
                  </div>
                )}
              </div>
            ) : (
              /* 3 Cards Mode when frame is an intermediate frame - Unified Blue Theme Across All Cards */
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
                {/* Card 1 (Left): Previous Keyframe */}
                {mapAroundData.prev && (
                  <div className="bg-blue-50/30 border border-blue-200 hover:border-blue-400 rounded-2xl p-4 flex flex-col items-center space-y-3 transition-all group shadow-sm">
                    <div className="text-xs sm:text-sm font-bold text-blue-800 bg-blue-100 border border-blue-200 px-3 py-1 rounded-full w-full text-center">
                      ⬅ Prev Keyframe (n={mapAroundData.prev.n})
                    </div>
                    {mapAroundData.prev.is_fallback_image && (
                      <div className="text-[11px] text-amber-800 bg-amber-50 px-2.5 py-1 rounded-lg border border-amber-200 font-mono text-center w-full font-semibold">
                        ⚠️ Keyframe #{mapAroundData.prev.frame_idx} missing — Displaying closest frame #{mapAroundData.prev.display_frame_idx}
                      </div>
                    )}
                    <div className="w-full aspect-video rounded-xl overflow-hidden bg-gray-100 relative border border-blue-200 shadow-inner">
                      <img
                        src={`http://127.0.0.1:6900/api/keyframes/${video_id}/${mapAroundData.prev.display_frame_idx || mapAroundData.prev.frame_idx}`}
                        onError={(e) => {
                          e.target.onerror = null;
                          e.target.src = `http://127.0.0.1:6900/api/files/${video_id}/${mapAroundData.prev.display_frame_idx || mapAroundData.prev.frame_idx}`;
                        }}
                        alt={`n=${mapAroundData.prev.n}`}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                      />
                    </div>
                    <div className="text-xs sm:text-sm font-mono text-blue-950 text-center font-bold">
                      Frame: #{mapAroundData.prev.frame_idx} {mapAroundData.prev.is_fallback_image ? `(Shown: #${mapAroundData.prev.display_frame_idx})` : ""} | {mapAroundData.prev.pts_time}s
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        addSelected(`${video_id}#${mapAroundData.prev.frame_idx}`);
                        setShowMapModal(false);
                      }}
                      className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs sm:text-sm rounded-xl transition-all shadow-md shadow-blue-600/20 flex items-center justify-center gap-1 active:scale-95"
                    >
                      + Add Keyframe (n={mapAroundData.prev.n})
                    </button>
                  </div>
                )}

                {/* Card 2 (Middle): Current Search Frame */}
                <div className="bg-blue-50/40 border-2 border-blue-500 rounded-2xl p-4 flex flex-col items-center space-y-3 transition-all shadow-md shadow-blue-500/10 group">
                  <div className="text-xs sm:text-sm font-extrabold text-blue-800 bg-blue-100 border border-blue-300 px-3 py-1 rounded-full w-full text-center">
                    ⏺ Current Search Frame
                  </div>
                  <div className="w-full aspect-video rounded-xl overflow-hidden bg-gray-100 relative border border-blue-300 shadow-inner">
                    <img
                      src={thumbnail}
                      alt={`Search Frame ${frame_id}`}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    />
                  </div>
                  <div className="text-xs sm:text-sm font-mono text-blue-950 text-center font-extrabold">
                    Frame: #{frame_id}
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      addSelected(id);
                      setShowMapModal(false);
                    }}
                    className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-extrabold text-xs sm:text-sm rounded-xl transition-all shadow-md shadow-blue-600/20 flex items-center justify-center gap-1 active:scale-95"
                  >
                    + Add Search Frame (#{frame_id})
                  </button>
                </div>

                {/* Card 3 (Right): Next Keyframe */}
                {mapAroundData.next && (
                  <div className="bg-blue-50/30 border border-blue-200 hover:border-blue-400 rounded-2xl p-4 flex flex-col items-center space-y-3 transition-all group shadow-sm">
                    <div className="text-xs sm:text-sm font-bold text-blue-800 bg-blue-100 border border-blue-200 px-3 py-1 rounded-full w-full text-center">
                      ➔ Next Keyframe (n={mapAroundData.next.n})
                    </div>
                    {mapAroundData.next.is_fallback_image && (
                      <div className="text-[11px] text-amber-800 bg-amber-50 px-2.5 py-1 rounded-lg border border-amber-200 font-mono text-center w-full font-semibold">
                        ⚠️ Keyframe #{mapAroundData.next.frame_idx} missing — Displaying closest frame #{mapAroundData.next.display_frame_idx}
                      </div>
                    )}
                    <div className="w-full aspect-video rounded-xl overflow-hidden bg-gray-100 relative border border-blue-200 shadow-inner">
                      <img
                        src={`http://127.0.0.1:6900/api/keyframes/${video_id}/${mapAroundData.next.display_frame_idx || mapAroundData.next.frame_idx}`}
                        onError={(e) => {
                          e.target.onerror = null;
                          e.target.src = `http://127.0.0.1:6900/api/files/${video_id}/${mapAroundData.next.display_frame_idx || mapAroundData.next.frame_idx}`;
                        }}
                        alt={`n=${mapAroundData.next.n}`}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                      />
                    </div>
                    <div className="text-xs sm:text-sm font-mono text-blue-950 text-center font-bold">
                      Frame: #{mapAroundData.next.frame_idx} {mapAroundData.next.is_fallback_image ? `(Shown: #${mapAroundData.next.display_frame_idx})` : ""} | {mapAroundData.next.pts_time}s
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        addSelected(`${video_id}#${mapAroundData.next.frame_idx}`);
                        setShowMapModal(false);
                      }}
                      className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs sm:text-sm rounded-xl transition-all shadow-md shadow-blue-600/20 flex items-center justify-center gap-1 active:scale-95"
                    >
                      + Add Keyframe (n={mapAroundData.next.n})
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Pinpoint First Occurrence / Action Boundary Inspector Modal */}
      {showPinpointModal && (
        <div
          onClick={() => setShowPinpointModal(false)}
          className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-2 sm:p-4 animate-fadeIn"
        >
          <div
            className="relative max-w-5xl max-h-[95vh] w-full bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="px-4 py-3 bg-slate-900 border-b border-slate-800 flex justify-between items-center shrink-0 flex-wrap gap-2">
              <div className="flex items-center gap-2 font-mono text-sm font-bold text-white">
                <span className="w-3 h-3 rounded-full bg-rose-500 animate-ping"></span>
                <span className="text-rose-400 font-extrabold flex items-center gap-1">
                  🎯 3-Tier Pinpoint Inspector:
                </span>
                <span className="text-blue-300 font-extrabold">{video_id}</span>
                <span className="text-gray-400">#</span>
                <span className="text-emerald-400 font-extrabold">{frame_id}</span>
                {temporalStep && (
                  <span className="px-2 py-0.5 rounded text-[10px] bg-blue-900/90 text-blue-200 border border-blue-600 font-mono font-bold">
                    Event {temporalStep}
                  </span>
                )}
                <span className="px-2 py-0.5 rounded text-[10px] bg-rose-950/80 text-rose-300 border border-rose-800 uppercase tracking-wider font-bold">
                  First Occurrence
                </span>
              </div>
              <button
                type="button"
                onClick={() => setShowPinpointModal(false)}
                className="w-7 h-7 bg-slate-800 hover:bg-rose-600 text-slate-300 hover:text-white rounded-lg flex items-center justify-center transition-all cursor-pointer font-bold text-xs"
              >
                ✕
              </button>
            </div>

            {/* Action Query Input Bar */}
            <div className="px-4 py-2.5 bg-slate-900/60 border-b border-slate-800/80 flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-300 shrink-0">Hành động:</span>
              <input
                type="text"
                value={pinpointQueryInput}
                onChange={(e) => setPinpointQueryInput(e.target.value)}
                placeholder="Nhập mô tả hành động (ví dụ: thịt bò chạm chảo, người mở cửa...)"
                className="flex-1 px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-rose-500 font-medium"
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleExecutePinpoint(pinpointQueryInput);
                }}
              />
              <button
                type="button"
                onClick={() => handleExecutePinpoint(pinpointQueryInput)}
                disabled={loadingPinpoint}
                className="px-3 py-1.5 bg-gradient-to-r from-rose-600 to-amber-600 hover:from-rose-500 hover:to-amber-500 text-white font-bold text-xs rounded-lg shadow transition-all flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
              >
                {loadingPinpoint ? "Đang quét..." : "🎯 Re-Pinpoint"}
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-4 overflow-y-auto flex-1 flex flex-col gap-4 min-h-0">
              {loadingPinpoint ? (
                <div className="flex flex-col items-center justify-center py-16 gap-4">
                  <div className="relative w-16 h-16">
                    <div className="absolute inset-0 rounded-full border-4 border-rose-500/20 border-t-rose-500 animate-spin"></div>
                    <div className="absolute inset-2 rounded-full border-4 border-amber-500/20 border-t-amber-500 animate-spin" style={{ animationDirection: "reverse" }}></div>
                  </div>
                  <div className="text-center space-y-1">
                    <p className="text-sm font-bold text-white">Đang thực thi Phễu lọc 3 tầng...</p>
                    <p className="text-xs text-slate-400">1. Cắt 200 Dense Frames (5 fps) ➔ 2. Chấm điểm Dense CLIP ➔ 3. VLM Xác thực ranh giới</p>
                  </div>
                </div>
              ) : pinpointError ? (
                <div className="p-4 bg-rose-950/40 border border-rose-800 rounded-xl text-rose-300 text-xs flex flex-col gap-2">
                  <div className="font-bold flex items-center gap-1 text-sm">
                    <span>⚠️ Lỗi định vị khoảnh khắc:</span>
                  </div>
                  <p>{pinpointError}</p>
                  <button
                    onClick={() => handleExecutePinpoint(pinpointQueryInput)}
                    className="self-start px-3 py-1 bg-rose-800 hover:bg-rose-700 text-white rounded text-xs font-bold mt-1"
                  >
                    Thử lại
                  </button>
                </div>
              ) : pinpointData ? (
                <div className="flex flex-col gap-4">
                  {/* Top Split: Exact Snapshot + Decision Card */}
                  <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
                    {/* Exact Frame Image */}
                    <div className="md:col-span-6 flex flex-col gap-1.5">
                      <div className="text-xs font-bold text-slate-300 flex items-center justify-between">
                        <span className="flex items-center gap-1 text-rose-400">
                          <span>📸 Exact First Occurrence Frame:</span>
                        </span>
                        <span className="font-mono text-emerald-400">#{pinpointData.exact_frame_idx}</span>
                      </div>
                      <div className="relative aspect-video w-full rounded-xl overflow-hidden bg-black border border-rose-500/50 shadow-lg shadow-rose-950/50 group">
                        <img
                          src={pinpointData.exact_frame_url}
                          alt={`Exact Frame ${pinpointData.exact_frame_idx}`}
                          className="w-full h-full object-cover"
                        />
                        <div className="absolute bottom-2 left-2 bg-black/80 backdrop-blur-sm px-2 py-1 rounded text-xs font-mono text-white flex gap-2 border border-slate-700">
                          <span className="text-rose-300 font-bold">⏱️ {pinpointData.formatted_time}</span>
                          <span className="text-slate-400">({pinpointData.exact_timestamp}s)</span>
                        </div>
                      </div>
                    </div>

                    {/* Reasoning & Actions Box */}
                    <div className="md:col-span-6 flex flex-col justify-between gap-3 bg-slate-900/90 p-4 rounded-xl border border-slate-800">
                      <div className="space-y-2.5">
                        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                          <span className="text-xs font-bold text-slate-400">Độ tin cậy VLM:</span>
                          <span className="px-2 py-0.5 bg-emerald-950 text-emerald-300 border border-emerald-800 rounded font-mono text-xs font-extrabold">
                            {Math.round((pinpointData.confidence || 0.9) * 100)}% Confidence
                          </span>
                        </div>

                        {/* Reasoning Text */}
                        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs text-slate-200 leading-relaxed">
                          <div className="text-[11px] font-bold text-amber-400 uppercase tracking-wide mb-1 flex items-center gap-1">
                            <span>🤖 Lời giải thích VLM:</span>
                          </div>
                          {pinpointData.reason}
                        </div>

                        {/* Submission Metadata */}
                        <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                          <div className="p-2 bg-slate-950 rounded-lg border border-slate-800 flex flex-col gap-1">
                            <span className="text-[10px] text-slate-400 uppercase">Exact Frame IDX:</span>
                            <div className="flex items-center justify-between">
                              <span className="font-bold text-white text-sm">{pinpointData.exact_frame_idx}</span>
                              <button
                                type="button"
                                onClick={() => {
                                  navigator.clipboard.writeText(String(pinpointData.exact_frame_idx));
                                  alert(`Copied Frame IDX: ${pinpointData.exact_frame_idx}`);
                                }}
                                className="px-1.5 py-0.5 bg-slate-800 hover:bg-slate-700 text-[10px] text-slate-300 rounded cursor-pointer"
                                title="Copy Frame IDX"
                              >
                                Copy
                              </button>
                            </div>
                          </div>

                          <div className="p-2 bg-slate-950 rounded-lg border border-slate-800 flex flex-col gap-1">
                            <span className="text-[10px] text-slate-400 uppercase">Map Keyframe (BTC):</span>
                            <div className="flex items-center justify-between">
                              <span className="font-bold text-emerald-400 text-sm">#{pinpointData.nearest_keyframe_id}</span>
                              <button
                                type="button"
                                onClick={() => {
                                  navigator.clipboard.writeText(`${video_id}#${pinpointData.nearest_keyframe_id}`);
                                  alert(`Copied: ${video_id}#${pinpointData.nearest_keyframe_id}`);
                                }}
                                className="px-1.5 py-0.5 bg-slate-800 hover:bg-slate-700 text-[10px] text-slate-300 rounded cursor-pointer"
                                title="Copy Keyframe ID"
                              >
                                Copy
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Action Buttons */}
                      <div className="flex items-center gap-2 pt-2 border-t border-slate-800">
                        <button
                          type="button"
                          onClick={() => {
                            if (onPlay) {
                              onPlay();
                            }
                          }}
                          className="flex-1 py-2 bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs rounded-lg transition-all flex items-center justify-center gap-1.5 shadow cursor-pointer"
                        >
                          <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M8 5v14l11-7z" />
                          </svg>
                          <span>Xem Video tại {pinpointData.formatted_time}</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            addSelected(`${video_id}#${pinpointData.nearest_keyframe_id || pinpointData.exact_frame_idx}`);
                            setShowPinpointModal(false);
                          }}
                          className="py-2 px-3 bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs rounded-lg transition-all flex items-center justify-center gap-1 shadow cursor-pointer"
                          title="Thêm frame này vào danh sách nộp bài"
                        >
                          + Thêm vào Payload
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Storyboard Grid Section */}
                  {pinpointData.storyboard_grid_url && (
                    <div className="flex flex-col gap-2 mt-2 pt-3 border-t border-slate-800">
                      <div className="flex items-center justify-between text-xs font-bold text-slate-300">
                        <span className="flex items-center gap-1 text-sky-400">
                          <span>🎞️ Chronological Storyboard (10 Candidate Frames):</span>
                        </span>
                        <span className="text-[11px] font-normal text-slate-400">
                          (Đã sắp xếp thứ tự thời gian & chấm điểm Dense CLIP)
                        </span>
                      </div>
                      <div className="w-full rounded-xl overflow-hidden bg-black border border-slate-800 shadow">
                        <img
                          src={pinpointData.storyboard_grid_url}
                          alt="Storyboard Grid"
                          className="w-full h-auto object-contain"
                        />
                      </div>
                    </div>
                  )}
                </div>
              ) : null}
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
