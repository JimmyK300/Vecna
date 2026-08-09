import { useState, useEffect, useRef } from "react";
import classNames from "classnames";

import PlayButton from "../assets/play-btn.svg";
import SearchButton from "../assets/search-btn.svg";
import NextButton from "../assets/next-btn.svg";
import { useSelected } from "./SelectedProvider.jsx";

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
  keyframes = [],
  shortlisted = false,
  onToggleShortlist = () => {},
  onToggleReject = () => {},
}) {
  const {
    selected,
    viewed,
    saved,
    addSelected,
    removeSelected,
    markViewed,
  } = useSelected();
  const isSelected = selected.includes(id);
  const isViewed = viewed.includes(id);
  const isSaved = saved.includes(id);
  const [isZoomed, setIsZoomed] = useState(false);
  const [showScores, setShowScores] = useState(false);
  const elementRef = useRef(null);

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
    if (!isZoomed) return;
    const handleKeyDown = (e) => {
      if (e.key === "Escape" || e.keyCode === 27) {
        setIsZoomed(false);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isZoomed]);
  
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
          <div className="absolute top-1 right-1 flex flex-wrap justify-end gap-1">
            {isViewed && <span className="frame-badge frame-badge-viewed">Viewed</span>}
            {isSelected && <span className="frame-badge frame-badge-selected">Staged</span>}
            {isSaved && <span className="frame-badge frame-badge-saved">Saved</span>}
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
