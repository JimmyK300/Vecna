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
}) {
  const { selected, addSelected, removeSelected } = useSelected();
  const isSelected = selected.includes(id);
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
  
  const handleSelect = () => {
    if (isSelected) {
      removeSelected(id);
    } else {
      addSelected(id);
    }
  };

  return (
    <>
      <div
        ref={elementRef}
        className={classNames("relative flex flex-col space-y-2 p-1 border-l-4 transition-all duration-200", {
          "bg-white hover:bg-gray-300": !isSelected && !timelineColor && !highlighted,
          "bg-black border-l-black scale-105 shadow-lg ring-4 ring-yellow-400": isSelected,
          "scale-105 shadow-lg ring-4 ring-cyan-500 bg-cyan-50 border-l-cyan-500": highlighted && !isSelected,
        }, !isSelected ? timelineColor : "")}
        onClick={handleSelect}
      >
        <div
          className="relative"
          onMouseEnter={() => setShowScores(true)}
          onMouseLeave={() => setShowScores(false)}
        >
          <img src={thumbnail} draggable="false" className="w-full h-auto" />
          {showScores && scores && (
            <div className="absolute bottom-0 left-0 right-0 bg-black bg-opacity-80 text-white text-xs p-1.5 space-y-0.5 pointer-events-none">
              <div className="flex justify-between"><span>Final:</span><span className="font-bold text-yellow-300">{scores.final?.toFixed(4) ?? '-'}</span></div>
              <div className="flex justify-between"><span>CLIP:</span><span className="font-bold text-green-300">{scores.clip?.toFixed(4) ?? '-'}</span></div>
              <div className="flex justify-between"><span>OCR:</span><span className="font-bold text-blue-300">{scores.ocr?.toFixed(4) ?? '-'}</span></div>
              <div className="flex justify-between"><span>ASR:</span><span className="font-bold text-purple-300">{scores.asr?.toFixed(4) ?? '-'}</span></div>
            </div>
          )}
        </div>
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
          className="flex flex-row bg-white rounded-md justify-end space-x-2 items-center"
        >
          {/* Zoom button (magnifying glass with plus sign) */}
          <svg
            onClick={() => setIsZoomed(true)}
            className="hover:bg-gray-200 active:bg-gray-300 rounded cursor-pointer p-0.5 text-gray-700"
            width="25px"
            height="25px"
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
            onClick={onPlay}
            className="hover:bg-gray-200 active:bg-gray-300"
            width="25em"
            src={PlayButton}
            draggable="false"
          />
          <img
            onClick={onSearchSimilar}
            className="hover:bg-gray-200 active:bg-gray-300"
            width="25em"
            src={SearchButton}
            draggable="false"
          />
          <img
            onClick={onSearchNearby}
            className="hover:bg-gray-200 active:bg-gray-300"
            width="25em"
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

export function FrameContainer({ children }) {
  return <div className="grid grid-cols-5 gap-2">{children}</div>;
}
