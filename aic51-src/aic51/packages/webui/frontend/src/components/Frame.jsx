import { useState, useEffect, useRef } from "react";
import classNames from "classnames";

import PlayButton from "../assets/play-btn.svg";
import SearchButton from "../assets/search-btn.svg";
import NextButton from "../assets/next-btn.svg";
import { useSelected } from "./SelectedProvider.jsx";
import { getOcrBoxes } from "../utils/queryState.js";

export function FrameItem({
  id,
  video_id,
  frame_id,
  thumbnail,
  timelineColor,
  highlighted,
  onPlay,
  onSearchSimilar,
  onSearchNearby,
  scores,
  ocr,
  ocrBoxes,
  keyframes = [],
  shortlisted = false,
  onToggleShortlist = () => {},
  onToggleReject = () => {},
}) {
  const {
    selected,
    viewed,
    submitted,
    addSelected,
    removeSelected,
    markViewed,
  } = useSelected();
  const isSelected = selected.includes(id);
  const isViewed = viewed.includes(id);
  const isSubmitted = submitted.includes(id);
  const normalizedOcrBoxes = getOcrBoxes(ocrBoxes);
  const [isZoomed, setIsZoomed] = useState(false);
  const [showScores, setShowScores] = useState(false);
  const [showOCR, setShowOCR] = useState(false);
  const [ocrText, setOcrText] = useState(ocr !== undefined ? ocr : null);
  const [loadingOCR, setLoadingOCR] = useState(false);
  const [copied, setCopied] = useState(false);
  const elementRef = useRef(null);

  useEffect(() => {
    if (ocr !== undefined) {
      setOcrText(ocr);
    }
  }, [ocr]);

  useEffect(() => {
    if (highlighted && elementRef.current) {
      // Small timeout to ensure DOM layout is ready
      const timer = setTimeout(() => {
        elementRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [highlighted]);

  useEffect(() => {
    if (!isZoomed && !showOCR) return;
    const handleKeyDown = (e) => {
      if (e.key === "Escape" || e.keyCode === 27) {
        setIsZoomed(false);
        setShowOCR(false);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isZoomed, showOCR]);
  
  const handleSelect = (event) => {
    event?.stopPropagation();
    if (isSelected) {
      removeSelected(id);
    } else {
      addSelected(id);
    }
  };

  const handlePlay = (event, selectedKeyframe = frame_id) => {
    event?.stopPropagation();
    markViewed(id);
    onPlay(selectedKeyframe);
  };

  const handleOpenOCR = async (e) => {
    e.stopPropagation();
    setShowOCR(true);
    if (!ocrText && ocrText !== "") {
      setLoadingOCR(true);
      try {
        const res = await fetch(`http://127.0.0.1:6900/api/frame/ocr/${video_id}/${frame_id}`);
        if (res.ok) {
          const data = await res.json();
          setOcrText(data.ocr || "");
        }
      } catch (err) {
        console.error("Failed to fetch frame OCR:", err);
      } finally {
        setLoadingOCR(false);
      }
    }
  };

  return (
    <>
      <div
        ref={elementRef}
        draggable
        onDragStart={(event) => {
          event.dataTransfer.setData("application/x-vecna-frame", id);
          event.dataTransfer.effectAllowed = "copy";
        }}
        data-frame-id={id}
        className={classNames("frame-card relative flex flex-col space-y-2 p-1 border-l-4 transition-all duration-200", {
          "bg-white hover:bg-gray-300": !isSelected && !timelineColor && !highlighted,
          "bg-black border-l-black scale-105 shadow-lg ring-4 ring-yellow-400": isSelected,
          "scale-105 shadow-lg ring-4 ring-cyan-500 bg-cyan-50 border-l-cyan-500": highlighted && !isSelected,
        }, !isSelected ? timelineColor : "")}
        onClick={handlePlay}
      >
        <div
          className="relative"
          onMouseEnter={() => setShowScores(true)}
          onMouseLeave={() => setShowScores(false)}
        >
          <img src={thumbnail} draggable="false" className="w-full h-auto" />
          {normalizedOcrBoxes.map((box, index) => (
            <span
              key={`${box.x}-${box.y}-${index}`}
              className="ocr-box-overlay"
              style={{ left: `${box.x}%`, top: `${box.y}%`, width: `${box.width}%`, height: `${box.height}%` }}
              title={box.text}
            />
          ))}
          <div className="absolute top-1 right-1 flex flex-wrap justify-end gap-1">
            {isViewed && <span className="frame-badge frame-badge-viewed">Viewed</span>}
            {isSelected && <span className="frame-badge frame-badge-selected">Staged</span>}
            {isSubmitted && <span className="frame-badge frame-badge-submitted">Sent</span>}
          </div>
          {showScores && scores && (
            <div className="absolute bottom-0 left-0 right-0 bg-black bg-opacity-80 text-white text-xs p-1.5 space-y-0.5 pointer-events-none">
              <div className="flex justify-between"><span>Final:</span><span className="font-bold text-yellow-300">{scores.final?.toFixed(4) ?? '-'}</span></div>
              <div className="flex justify-between"><span>CLIP:</span><span className="font-bold text-green-300">{scores.clip?.toFixed(4) ?? '-'}</span></div>
              <div className="flex justify-between"><span>OCR:</span><span className="font-bold text-blue-300">{scores.ocr?.toFixed(4) ?? '-'}</span></div>
              <div className="flex justify-between"><span>ASR:</span><span className="font-bold text-purple-300">{scores.asr?.toFixed(4) ?? '-'}</span></div>
            </div>
          )}
        </div>
        {keyframes.length > 1 && (
          <div className="storyboard-strip" aria-label={`${keyframes.length} temporal keyframes`}>
            {keyframes.map((keyframe, index) => (
              <button
                type="button"
                key={`${keyframe}-${index}`}
                className="storyboard-frame"
                onClick={(event) => handlePlay(event, keyframe)}
                title={`Open keyframe ${keyframe}`}
              >
                <img src={`http://127.0.0.1:6900/api/files/${video_id}/${keyframe}`} alt={`Keyframe ${keyframe}`} loading="lazy" />
                <span>{keyframe}</span>
              </button>
            ))}
          </div>
        )}
        <div className="absolute top-0 left-0 space-x-2 flex flex-row bg-black bg-opacity-50 px-1">
          <div className="text-sm text-white">{frame_id}</div>
          <div className="text-sm text-nowrap overflow-hidden text-white">
            {video_id}
          </div>
        </div>
        <div
          onClick={(e) => {
            e.stopPropagation();
          }}
          className="flex flex-row bg-white rounded-md justify-end space-x-1.5 items-center p-0.5"
        >
          <button type="button" className={isSelected ? "frame-action active" : "frame-action"} onClick={handleSelect} title="Stage this candidate">
            {isSelected ? "Staged" : "Stage"}
          </button>
          {/* OCR Transcript Button */}
          <svg
            onClick={handleOpenOCR}
            className="hover:bg-gray-200 active:bg-gray-300 rounded cursor-pointer p-0.5 text-blue-600 hover:text-blue-800 transition-colors"
            width="24px"
            height="24px"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            title="Xem OCR Transcript"
          >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
            <line x1="16" y1="13" x2="8" y2="13"></line>
            <line x1="16" y1="17" x2="8" y2="17"></line>
            <line x1="10" y1="9" x2="8" y2="9"></line>
          </svg>

          {/* Zoom button */}
          <svg
            onClick={() => setIsZoomed(true)}
            className="hover:bg-gray-200 active:bg-gray-300 rounded cursor-pointer p-0.5 text-gray-700"
            width="24px"
            height="24px"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            title="Zoom image"
          >
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            <line x1="11" y1="8" x2="11" y2="14"></line>
            <line x1="8" y1="11" x2="14" y2="11"></line>
          </svg>
          <img
            onClick={handlePlay}
            className="hover:bg-gray-200 active:bg-gray-300 cursor-pointer"
            width="24em"
            src={PlayButton}
            draggable="false"
            title="Play video"
          />
          <button type="button" className={shortlisted ? "frame-action active" : "frame-action"} onClick={(event) => { event.stopPropagation(); onToggleShortlist(); }} title="Shortlist this candidate">★</button>
          <button type="button" className="frame-action frame-action-reject" onClick={(event) => { event.stopPropagation(); onToggleReject(); }} title="Reject this candidate">×</button>
          <img
            onClick={(event) => { event.stopPropagation(); onSearchSimilar(frame_id); }}
            className="hover:bg-gray-200 active:bg-gray-300 cursor-pointer"
            width="24em"
            src={SearchButton}
            draggable="false"
            title="Search similar"
          />
          <img
            onClick={(event) => { event.stopPropagation(); onSearchNearby(frame_id); }}
            className="hover:bg-gray-200 active:bg-gray-300 cursor-pointer"
            width="24em"
            src={NextButton}
            draggable="false"
            title="Search nearby keyframes"
          />
        </div>
      </div>

      {/* OCR Modal */}
      {showOCR && (
        <div
          onClick={() => setShowOCR(false)}
          className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-75 z-50 p-4 cursor-pointer"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="relative max-w-xl w-full bg-white rounded-xl shadow-2xl p-4 flex flex-col space-y-3 cursor-default"
          >
            <div className="flex justify-between items-center border-b pb-2">
              <div className="flex items-center space-x-2 font-bold text-gray-800 text-sm">
                <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <span>OCR Transcript — {video_id}#{frame_id}</span>
              </div>
              <button
                onClick={() => setShowOCR(false)}
                className="text-gray-400 hover:text-gray-600 font-bold px-2 py-1 rounded text-base"
              >
                ✕
              </button>
            </div>

            <div className="max-h-[60vh] overflow-y-auto bg-slate-50 border rounded-lg p-3 text-sm font-mono text-slate-800 leading-relaxed whitespace-pre-wrap select-text">
              {loadingOCR ? (
                <div className="text-gray-500 animate-pulse">Đang tải văn bản OCR...</div>
              ) : (ocrText && String(ocrText).trim()) ? (
                typeof ocrText === "string" ? ocrText : JSON.stringify(ocrText, null, 2)
              ) : (
                <div className="text-gray-400 italic">Không tìm thấy văn bản OCR được trích xuất cho khung hình này.</div>
              )}
            </div>

            <div className="flex justify-between items-center pt-1">
              <span className="text-xs text-gray-500 font-medium">
                {(ocrText && ocrText.trim()) ? `${ocrText.trim().length} ký tự` : ""}
              </span>
              <div className="flex space-x-2">
                {(ocrText && String(ocrText).trim()) && (
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(typeof ocrText === "string" ? ocrText : JSON.stringify(ocrText));
                      setCopied(true);
                      setTimeout(() => setCopied(false), 2000);
                    }}
                    className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white rounded text-xs font-semibold flex items-center space-x-1"
                  >
                    <span>{copied ? "✓ Đã chép!" : "Sao chép văn bản"}</span>
                  </button>
                )}
                <button
                  onClick={() => setShowOCR(false)}
                  className="px-3 py-1.5 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded text-xs font-semibold"
                >
                  Đóng
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {isZoomed && (
        <div
          onClick={() => setIsZoomed(false)}
          className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-75 z-50 cursor-zoom-out"
        >
          <div 
            className="relative max-w-[95vw] w-fit max-h-[95vh] p-2 bg-white rounded-xl shadow-2xl flex flex-col items-center"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setIsZoomed(false)}
              className="absolute top-2 right-2 px-3 py-1 bg-red-600 text-white rounded-lg hover:bg-red-700 font-bold text-xs shadow-md active:bg-red-800"
            >
              Close
            </button>
            <img
              src={thumbnail.replace("/api/files/", "/api/keyframes/")}
              className="max-w-[90vw] max-h-[85vh] object-contain rounded-lg shadow-inner bg-gray-100"
              alt="Enlarged keyframe"
            />
            <div className="mt-2 text-sm font-semibold text-gray-800">
              Video ID: {video_id} | Frame ID: {frame_id}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export function FrameContainer({ children, density = 220 }) {
  const minWidth = Number(density) || 220;
  return (
    <div className="frame-grid" style={{ "--frame-min-width": `${minWidth}px` }}>
      {children}
    </div>
  );
}
