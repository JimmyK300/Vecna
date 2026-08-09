import { useFetcher } from "react-router-dom";
import { createContext, useEffect, useContext, useState, useRef } from "react";
import classNames from "classnames";
import { AuthContext } from "./AuthProvider";
import { useSelected } from "./SelectedProvider.jsx";
import { getFrameInfo, getVideoTranscript, getVideoKeyframes } from "../services/search.js";
import { getShortcutAction } from "../utils/keyboardShortcuts.js";
export const VideoContext = createContext({ playVideo: null });

export default function VideoProvider({ children }) {
  const [frameInfo, setFrameInfo] = useState(null);
  const playVideo = async (f, keyframe) => {
    const res = await getFrameInfo(f.video_id, keyframe);
    res.frame_id = keyframe;
    setFrameInfo(res);
  };
  const handleOnCancle = () => {
    setFrameInfo(null);
  };
  return (
    <VideoContext.Provider
      value={{
        playVideo,
      }}
    >
      {frameInfo !== null && (
        <VideoPlayer key={`${frameInfo.video_id}#${frameInfo.frame_id}`} frameInfo={frameInfo} onCancle={handleOnCancle} />
      )}
      {children}
    </VideoContext.Provider>
  );
}
export function usePlayVideo() {
  const { playVideo } = useContext(VideoContext);
  return playVideo;
}
function VideoPlayer({ frameInfo, onCancle }) {
  const { evaluationIds, submitAnswer } = useContext(AuthContext);
  const {
    selected,
    addSelected,
    removeSelected,
    toggleShortlist,
    toggleReject,
  } = useSelected();
  const fetcher = useFetcher({ key: "answers" });
  const videoElementRef = useRef(null);
  const playerShellRef = useRef(null);
  const currentFrameIdRef = useRef("");
  const [frameCounter, setFrameCounter] = useState(0);
  const [seekStep, setSeekStep] = useState(2);
  const seekStepRef = useRef(2);

  const [transcript, setTranscript] = useState([]);
  const [activeSegmentIndex, setActiveSegmentIndex] = useState(-1);
  const [searchTerm, setSearchTerm] = useState("");
  const transcriptContainerRef = useRef(null);

  const timelineRef = useRef(null);
  const [isScrubbing, setIsScrubbing] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [workspaceHeight, setWorkspaceHeight] = useState(500);
  const [evidenceTab, setEvidenceTab] = useState("all");

  const displayEvaluationIds = [
    { id: "TKIS", name: "TKIS" },
    { id: "VKIS", name: "VKIS" },
    { id: "QA", name: "QA" },
    { id: "TR", name: "TR" },
    ...evaluationIds
  ];

  const [selectedQueryId, setSelectedQueryId] = useState(
    displayEvaluationIds.length > 0 ? displayEvaluationIds[0].id : ""
  );

  const handleSeekStepChange = (e) => {
    const val = parseFloat(e.target.value) || 0;
    setSeekStep(val);
    seekStepRef.current = val;
  };

  const toggleFullscreen = async () => {
    if (!playerShellRef.current) return;
    if (document.fullscreenElement) {
      await document.exitFullscreen();
    } else {
      await playerShellRef.current.requestFullscreen();
    }
  };

  useEffect(() => {
    const handleFullscreenChange = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  const [keyframes, setKeyframes] = useState([]);

  useEffect(() => {
    async function loadTranscript() {
      try {
        const data = await getVideoTranscript(frameInfo.video_id);
        setTranscript(data);
      } catch (err) {
        console.error("Failed to load transcript", err);
      }
    }
    loadTranscript();
  }, [frameInfo.video_id]);

  useEffect(() => {
    async function loadKeyframes() {
      try {
        const data = await getVideoKeyframes(frameInfo.video_id);
        setKeyframes(data);
      } catch (err) {
        console.error("Failed to load keyframes", err);
      }
    }
    loadKeyframes();
  }, [frameInfo.video_id]);

  const handleTimelineScrub = (e) => {
    if (!videoElementRef.current || !timelineRef.current) return;
    const rect = timelineRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const relativeX = Math.max(0, Math.min(1, x / rect.width));
    if (videoElementRef.current.duration) {
      videoElementRef.current.currentTime = relativeX * videoElementRef.current.duration;
    }
  };

  const handleMouseDown = (e) => {
    e.preventDefault();
    setIsScrubbing(true);
    handleTimelineScrub(e);
  };

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (isScrubbing) {
        handleTimelineScrub(e);
      }
    };
    const handleMouseUp = () => {
      if (isScrubbing) {
        setIsScrubbing(false);
      }
    };

    if (isScrubbing) {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
    }

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isScrubbing]);

  const targetTimelineCount = 20;
  const sampledKeyframes = [];
  if (keyframes.length > 0) {
    for (let i = 0; i < targetTimelineCount; i++) {
      const idx = Math.floor((i / (targetTimelineCount - 1)) * (keyframes.length - 1));
      sampledKeyframes.push(keyframes[idx]);
    }
  }

  const duration = videoElementRef.current ? videoElementRef.current.duration : 0;
  const currentPercentage = duration > 0 ? ((frameCounter / frameInfo.fps) / duration) * 100 : 0;

  useEffect(() => {
    if (transcript.length === 0) return;
    const fps = frameInfo.fps;
    const currentTime = frameCounter / fps;
    const activeIdx = transcript.findIndex(
      (item) => currentTime >= item.start_time && currentTime <= item.end_time
    );
    if (activeIdx !== activeSegmentIndex) {
      setActiveSegmentIndex(activeIdx);
      if (activeIdx !== -1) {
        const activeEl = document.getElementById(`asr-seg-${activeIdx}`);
        if (activeEl && transcriptContainerRef.current) {
          activeEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      }
    }
  }, [frameCounter, transcript, activeSegmentIndex, frameInfo.fps]);

  useEffect(() => {
    const fps = Number(frameInfo.fps) || 30;
    const videoElement = videoElementRef.current;
    if (!videoElement) return undefined;
    videoElement.currentTime = frameInfo.time || parseInt(frameInfo.frame_id, 10) / fps - 0.5;
    videoElement.focus();

    const handleKeyDown = (event) => {
      const isInInput = ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName);
      if (event.key === "Escape") {
        event.preventDefault();
        onCancle();
        return;
      }
      if (event.key === "Enter" && event.shiftKey) {
        event.preventDefault();
        document.querySelector("#answer-form input[type=submit]")?.click();
        return;
      }
      if (event.key === "Enter" && !isInInput) {
        event.preventDefault();
        document.querySelector("#answer-form input[name=answer]")?.focus();
        return;
      }

      const action = getShortcutAction(event, { isInput: isInInput });
      if (!action) return;
      event.preventDefault();
      if (action === "focus-answer") {
        document.querySelector("#answer-form input[name=answer]")?.focus();
      } else if (action === "toggle-play") {
        if (videoElement.paused) videoElement.play();
        else videoElement.pause();
      } else if (action === "seek-previous") {
        videoElement.currentTime = Math.max(videoElement.currentTime - seekStepRef.current, 0);
      } else if (action === "seek-next") {
        videoElement.currentTime = Math.min(videoElement.currentTime + seekStepRef.current, videoElement.duration || Infinity);
      } else if (action === "frame-previous") {
        videoElement.currentTime = Math.max(videoElement.currentTime - 1 / fps, 0);
      } else if (action === "frame-next") {
        videoElement.currentTime = Math.min(videoElement.currentTime + 1 / fps, videoElement.duration || Infinity);
      } else if (action === "speed-down") {
        videoElement.playbackRate = Math.max(videoElement.playbackRate - 0.25, 0.25);
      } else if (action === "speed-up") {
        videoElement.playbackRate = Math.min(videoElement.playbackRate + 0.25, 4);
      } else if (action === "toggle-shortlist") {
        toggleShortlist(currentFrameIdRef.current);
      } else if (action === "toggle-reject") {
        toggleReject(currentFrameIdRef.current);
      }
    };

    document.addEventListener("keydown", handleKeyDown, true);
    const intervalId = setInterval(() => {
      setFrameCounter(videoElement.currentTime * fps);
    }, 20);
    return () => {
      document.removeEventListener("keydown", handleKeyDown, true);
      clearInterval(intervalId);
    };
  }, [frameInfo, onCancle, toggleReject, toggleShortlist]);

  const currentFrameStr = String(Math.round(frameCounter)).padStart(6, '0');
  const currentFrameId = `${frameInfo.video_id}#${currentFrameStr}`;
  currentFrameIdRef.current = currentFrameId;
  const isFrameSelected = selected.includes(currentFrameId);
  const ocrEvidence = frameInfo.ocr || frameInfo.ocr_text || "";
  const ocrEvidenceText = typeof ocrEvidence === "string" ? ocrEvidence : JSON.stringify(ocrEvidence, null, 2);

  const selectedFramesOfThisVideo = selected
    .filter(id => id.startsWith(frameInfo.video_id + "#"))
    .map(id => id.split("#")[1])
    .sort((a, b) => parseInt(a) - parseInt(b));

  const selectedMarkers = selectedFramesOfThisVideo.map((frameNum) => ({
    frameNum,
    left: duration > 0 ? (parseInt(frameNum, 10) / (duration * frameInfo.fps)) * 100 : 0,
  }));

  const jumpToFrame = (frameNum) => {
    if (videoElementRef.current) {
      videoElementRef.current.currentTime = parseInt(frameNum) / frameInfo.fps;
    }
  };

  const handleResizeStart = (event) => {
    event.preventDefault();
    const startY = event.clientY;
    const startHeight = workspaceHeight;
    const handleMove = (moveEvent) => {
      const nextHeight = startHeight + startY - moveEvent.clientY;
      setWorkspaceHeight(Math.min(Math.max(nextHeight, 280), window.innerHeight - 48));
    };
    const handleUp = () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    };
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
  };

  return (
      <div
        ref={playerShellRef}
        className="verification-workspace"
        style={{ height: `${workspaceHeight}px` }}
    >
      <button type="button" className="workspace-resize-handle" onMouseDown={handleResizeStart} aria-label="Resize verification workspace" title="Drag to resize verification workspace">
        <span />
      </button>
      <div
        className={classNames("video-player-modal p-4 bg-white flex flex-col shadow-2xl animate-fade-in", {
          "video-player-modal-fullscreen": isFullscreen,
        })}
      >
        <div className="flex flex-row justify-between items-start mb-3">
          <div className="flex flex-row gap-6 text-sm">
            <div>
              <div className="">
                <span className="font-bold">Video ID</span>
                {": "}
                {frameInfo.video_id}
              </div>
              <div className="">
                {" "}
                <span className="font-bold">Frame ID</span>
                {": "}
                {frameInfo.frame_id}
              </div>
              <div className="">
                {" "}
                <span className="font-bold">Frame Counter</span>
                {": "}
                {parseInt(frameCounter)}
              </div>
              <div className="flex items-center gap-1 mt-1">
                <span className="font-bold">Seek Step (s)</span>
                {": "}
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={seekStep}
                  onChange={handleSeekStepChange}
                  className="w-12 text-center text-xs border border-gray-400 rounded focus:outline-none focus:border-blue-500 font-medium"
                />
              </div>
              <button
                id="toggle-select-frame-btn"
                onClick={() => {
                  if (isFrameSelected) {
                    removeSelected(currentFrameId);
                  } else {
                    addSelected(currentFrameId);
                  }
                }}
                className={classNames(
                  "mt-2 px-3 py-1 text-xs font-semibold rounded-lg border transition-all duration-150 shadow-sm",
                  {
                    "bg-orange-500 hover:bg-orange-600 text-white border-orange-600": isFrameSelected,
                    "bg-white hover:bg-gray-50 text-slate-700 border-slate-300": !isFrameSelected,
                  }
                )}
              >
                {isFrameSelected ? "Deselect Frame" : "Select Frame"}
              </button>
            </div>

            {selectedFramesOfThisVideo.length > 0 && (
              <div className="border-l border-slate-200 pl-4 flex flex-col justify-between">
                <div>
                  <div className="font-bold text-slate-700 mb-1">Selected in this video:</div>
                  <div className="flex flex-wrap gap-1 max-w-[20rem]">
                    {selectedFramesOfThisVideo.map((frameNum) => (
                      <span
                        key={frameNum}
                        className={classNames(
                          "inline-flex items-center gap-1 font-mono text-[10px] px-1.5 py-0.5 rounded border transition-colors duration-150 shadow-sm group",
                          {
                            "bg-orange-500 border-orange-600 text-white font-semibold": frameNum === currentFrameStr,
                            "bg-orange-550 bg-orange-50 border-orange-200 text-orange-700 hover:bg-orange-100 hover:border-orange-300": frameNum !== currentFrameStr,
                          }
                        )}
                      >
                        <span 
                          onClick={() => jumpToFrame(frameNum)}
                          className="cursor-pointer"
                          title={frameNum === currentFrameStr ? "Currently showing" : "Click to seek to this frame"}
                        >
                          {frameNum}
                        </span>
                        <span
                          onClick={(e) => {
                            e.stopPropagation();
                            removeSelected(`${frameInfo.video_id}#${frameNum}`);
                          }}
                          className="cursor-pointer font-bold opacity-0 group-hover:opacity-100 hover:text-red-650 text-slate-400 pl-0.5 transition-all duration-150 text-[9px]"
                          title="Remove frame"
                        >
                          ✕
                        </span>
                      </span>
                    ))}
                  </div>
                </div>
                <div className="mt-2 text-[10px] text-slate-600 font-mono select-all bg-slate-50 border border-slate-200 rounded px-1.5 py-0.5" title="Double click to copy">
                  {selectedQueryId}-{frameInfo.video_id}-{selectedFramesOfThisVideo.join(",")}
                </div>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button type="button" onClick={toggleFullscreen} className="toolbar-button" title="Toggle fullscreen">
              {isFullscreen ? "Exit fullscreen" : "Fullscreen"}
            </button>
            <button type="button" onClick={onCancle} className="toolbar-button" title="Close verification workspace">Close</button>
          </div>
          <fetcher.Form
            id="answer-form"
            onSubmit={(e) => {
              e.preventDefault();
              const formData = new FormData(e.currentTarget);
              const data = Object.fromEntries(formData);
              const newAnswer = {
                ...data,
                video_id: frameInfo.video_id,
                frame_id: String(Math.round(frameCounter)),
                frame_counter: frameCounter,
                time: videoElementRef.current.currentTime,
              };
              submitAnswer(newAnswer);
            }}
          >
            <div className="flex flex-row">
              <select
                required
                type="text"
                name="query_id"
                value={selectedQueryId}
                onChange={(e) => setSelectedQueryId(e.target.value)}
                placeholder="evaluationIds"
                className="flex-1 py-1 px-2 border-black border-r-2 min-w-0 focus:outline-none"
              >
                {displayEvaluationIds.map((e) => (
                  <option key={e.id} value={e.id}>{e.name}</option>
                ))}
              </select>
              <input
                type="text"
                name="answer"
                placeholder="Answer"
                autoComplete="off"
                className="flex-[2_2_0%] py-1 px-2 min-w-0 focus:outline-none"
              />
              <input
                type="submit"
                value="Submit"
                className="text-xl px-4 py-1 bg-sky-100 border border-black rounded-xl focus:outline-none hover:bg-sky-200 active:bg-sky-300"
              />
            </div>
          </fetcher.Form>
        </div>

        <div className="flex flex-row gap-4 overflow-hidden items-start">
          {/* Left: Video and playback controls */}
          <div className="flex flex-col flex-1 min-w-[50vw]">
            <video
              ref={videoElementRef}
              id="playing-vide"
              key={frameInfo.video_uri}
              controls
              autoPlay
              className="w-full h-[26rem] object-contain bg-black rounded-lg shadow-inner"
            >
              <source src={frameInfo.video_uri} type="video/mp4" />
            </video>

            {/* Keyframe Timeline Strip */}
            <div
              ref={timelineRef}
              onMouseDown={handleMouseDown}
              className="mt-1 flex flex-row w-full py-0.5 items-center min-h-[4.5rem] bg-slate-950 rounded border border-slate-800 overflow-hidden relative select-none cursor-ew-resize shadow-md"
            >
              {/* Playhead line */}
              {videoElementRef.current && (
                <div
                  style={{ left: `${currentPercentage}%` }}
                  className="absolute top-0 bottom-0 w-1 bg-red-500 z-20 pointer-events-none shadow-md shadow-red-500/80"
                />
              )}

              {selectedMarkers.map(({ frameNum, left }) => (
                <div
                  key={frameNum}
                  className="absolute top-0 bottom-0 w-1 bg-orange-400 z-10 pointer-events-none shadow-md"
                  style={{ left: `${Math.min(100, Math.max(0, left))}%` }}
                  title={`Selected frame ${frameNum}`}
                />
              ))}

              {sampledKeyframes.length === 0 ? (
                <div className="text-slate-500 text-xs text-center w-full py-4 pointer-events-none">Loading timeline keyframes...</div>
              ) : (
                sampledKeyframes.map((kf, i) => {
                  return (
                    <div
                      key={kf + "-" + i}
                      className="flex-1 h-14 relative group overflow-hidden pointer-events-none"
                    >
                      <img
                        src={`http://127.0.0.1:6900/api/files/${frameInfo.video_id}/${kf}`}
                        alt={kf}
                        loading="lazy"
                        className="h-full w-full object-cover bg-black"
                      />
                    </div>
                  );
                })
              )}
            </div>
          </div>
          {/* Right: Live Transcript */}
          <div className="flex flex-col w-96 h-[32rem] border border-slate-200 rounded-lg bg-slate-50 shadow-sm overflow-hidden">
            <div className="evidence-panel-heading">
              <div className="evidence-tabs" role="tablist" aria-label="Evidence views">
                {["all", "transcript", "ocr"].map((tab) => (
                  <button key={tab} type="button" role="tab" aria-selected={evidenceTab === tab} className={evidenceTab === tab ? "active" : ""} onClick={() => setEvidenceTab(tab)}>
                    {tab === "all" ? "All" : tab === "transcript" ? "Transcript" : "OCR"}
                  </button>
                ))}
              </div>
              {evidenceTab !== "ocr" && <input
                type="text"
                placeholder="Search transcript..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="text-xs py-1 px-2 border border-slate-300 rounded focus:outline-none focus:border-blue-500 font-medium w-48 shadow-sm transition-colors duration-150"
              />}
            </div>
            {(evidenceTab === "all" || evidenceTab === "transcript") && <div
              ref={transcriptContainerRef}
              className="flex-grow overflow-y-auto p-2 space-y-1.5"
            >
              {transcript.length === 0 ? (
                <div className="text-slate-400 text-center py-8 text-xs font-medium">No transcript available</div>
              ) : (
                transcript.map((item, idx) => {
                  const fps = frameInfo.fps;
                  const currentTime = frameCounter / fps;
                  const isActive = currentTime >= item.start_time && currentTime <= item.end_time;
                  
                  const matchesSearch =
                    searchTerm &&
                    item.text.toLowerCase().includes(searchTerm.toLowerCase());

                  return (
                    <div
                      key={idx}
                      id={`asr-seg-${idx}`}
                      onClick={() => {
                        if (videoElementRef.current) {
                          videoElementRef.current.currentTime = item.start_time;
                        }
                      }}
                      className={classNames(
                        "p-2.5 rounded-lg border-l-4 cursor-pointer transition-all duration-200 text-xs shadow-sm",
                        {
                          "bg-blue-50 border-l-blue-600 font-medium text-blue-950 ring-1 ring-blue-100": isActive,
                          "bg-yellow-50/70 border-l-yellow-400 text-slate-800": matchesSearch && !isActive,
                          "bg-white border-l-transparent text-slate-700 hover:bg-slate-100/70 hover:border-l-slate-300": !isActive && !matchesSearch,
                        }
                      )}
                    >
                      <div className="flex justify-between text-[10px] text-slate-400 mb-1 font-mono">
                        <span>{formatTime(item.start_time)} - {formatTime(item.end_time)}</span>
                        <span>Frame {item.start_frame}</span>
                      </div>
                      <div className="leading-relaxed break-words">{highlightTranscript(item.text, searchTerm)}</div>
                    </div>
                  );
                })
              )}
            </div>}
            {(evidenceTab === "all" || evidenceTab === "ocr") && <div className="evidence-ocr">
              <p className="eyebrow">OCR evidence</p>
              {ocrEvidenceText ? <pre>{ocrEvidenceText}</pre> : <span className="helper-text">No OCR evidence returned for this frame.</span>}
            </div>}
          </div>
        </div>
      </div>
    </div>
  );
}

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 10);
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}.${ms}`;
}

function highlightTranscript(text, searchTerm) {
  if (!searchTerm.trim()) return text;
  const escapedSearchTerm = searchTerm.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const parts = text.split(new RegExp(`(${escapedSearchTerm})`, "ig"));
  return parts.map((part, index) => (
    part.toLowerCase() === searchTerm.toLowerCase()
      ? <mark key={`${part}-${index}`} className="transcript-highlight">{part}</mark>
      : part
  ));
}
