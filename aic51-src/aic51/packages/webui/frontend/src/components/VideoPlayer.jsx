import { useFetcher } from "react-router-dom";
import { createContext, useEffect, useContext, useState, useRef } from "react";
import classNames from "classnames";
import { AuthContext } from "./AuthProvider.jsx";
import { useSelected } from "./SelectedProvider.jsx";
import { getFrameInfo, getVideoTranscript, getVideoKeyframes, getVideoMapKeyframes } from "../services/search.js";

export const VideoContext = createContext({ playVideo: null });

export default function VideoProvider({ children }) {
  const [frameInfo, setFrameInfo] = useState(null);

  const playVideo = async (f, keyframe) => {
    const vId = typeof f === "string" ? f : f?.video_id;
    const kId = keyframe || (typeof f === "object" ? f?.frame_id : 0);
    if (!vId || vId === "undefined" || vId === "null") return;

    try {
      const res = await getFrameInfo(vId, kId);
      res.frame_id = kId;
      setFrameInfo(res);
    } catch (err) {
      console.warn("getFrameInfo failed, using constructed frameInfo fallback:", err);
      const domain = window.location.origin;
      setFrameInfo({
        id: `${vId}#${kId}`,
        video_id: vId,
        frame_id: String(kId),
        fps: 25,
        video_uri: `${domain}/api/files/${vId}`,
      });
    }
  };

  const handleOnCancel = () => {
    setFrameInfo(null);
  };

  return (
    <VideoContext.Provider value={{ playVideo }}>
      {frameInfo !== null && (
        <VideoPlayer frameInfo={frameInfo} onCancel={handleOnCancel} />
      )}
      {children}
    </VideoContext.Provider>
  );
}

export function usePlayVideo() {
  const { playVideo } = useContext(VideoContext);
  return playVideo;
}

export function VideoPlayer({ frameInfo, onCancel }) {
  const { evaluationIds, submitAnswer } = useContext(AuthContext);
  const { selected, addSelected, removeSelected } = useSelected();
  const fetcher = useFetcher({ key: "answers" });
  const videoElementRef = useRef(null);
  const videoWrapperRef = useRef(null);

  const [frameCounter, setFrameCounter] = useState(0);
  const [seekStep, setSeekStep] = useState(2);
  const seekStepRef = useRef(2);

  const [transcript, setTranscript] = useState([]);
  const [activeSegmentIndex, setActiveSegmentIndex] = useState(-1);
  const [searchTerm, setSearchTerm] = useState("");
  const transcriptContainerRef = useRef(null);

  const timelineRef = useRef(null);
  const [isScrubbing, setIsScrubbing] = useState(false);
  const [keyframes, setKeyframes] = useState([]);

  const displayEvaluationIds = [
    { id: "TKIS", name: "TKIS" },
    { id: "VKIS", name: "VKIS" },
    { id: "QA", name: "QA" },
    { id: "TRAKE", name: "TRAKE" },
    ...evaluationIds,
  ];

  const [selectedQueryId, setSelectedQueryId] = useState(
    displayEvaluationIds[0]?.id || "TKIS"
  );

  const handleSeekStepChange = (e) => {
    const val = parseFloat(e.target.value) || 0;
    setSeekStep(val);
    seekStepRef.current = val;
  };

  // Fullscreen Video + Diagram Container (Hotkey F)
  const toggleVideoFullscreen = () => {
    if (!videoWrapperRef.current) return;
    if (!document.fullscreenElement) {
      videoWrapperRef.current.requestFullscreen().catch((err) => console.error(err));
    } else {
      document.exitFullscreen().catch((err) => console.error(err));
    }
  };

  // Load Transcript
  useEffect(() => {
    if (!frameInfo?.video_id) return;
    getVideoTranscript(frameInfo.video_id)
      .then((data) => {
        setTranscript(Array.isArray(data) ? data : []);
      })
      .catch(() => setTranscript([]));
  }, [frameInfo?.video_id]);

  // Load Keyframes Timeline Strip
  useEffect(() => {
    if (!frameInfo?.video_id) return;
    getVideoKeyframes(frameInfo.video_id)
      .then((res) => {
        const list = Array.isArray(res) ? res : (res?.keyframes || []);
        setKeyframes(list);
      })
      .catch(() => setKeyframes([]));
  }, [frameInfo?.video_id]);

  const keyframesRef = useRef([]);
  useEffect(() => {
    keyframesRef.current = keyframes;
  }, [keyframes]);

  // Load Official BTC Map-Keyframes Data
  const [mapBTCKeyframes, setMapBTCKeyframes] = useState([]);
  const mapBTCKeyframesRef = useRef([]);

  useEffect(() => {
    mapBTCKeyframesRef.current = mapBTCKeyframes;
  }, [mapBTCKeyframes]);

  useEffect(() => {
    if (!frameInfo?.video_id) return;
    getVideoMapKeyframes(frameInfo.video_id)
      .then((res) => {
        if (res && res.available && Array.isArray(res.keyframes)) {
          setMapBTCKeyframes(res.keyframes);
        } else {
          setMapBTCKeyframes([]);
        }
      })
      .catch(() => setMapBTCKeyframes([]));
  }, [frameInfo?.video_id]);


  // Timeline Scrubbing Handler (CapCut Timeline Bar)
  const handleTimelineScrub = (e) => {
    if (!videoElementRef.current || !timelineRef.current) return;
    const rect = timelineRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const relativeX = Math.max(0, Math.min(1, x / rect.width));
    if (videoElementRef.current.duration) {
      videoElementRef.current.currentTime =
        relativeX * videoElementRef.current.duration;
    }
  };

  const handleMouseDown = (e) => {
    e.preventDefault();
    setIsScrubbing(true);
    handleTimelineScrub(e);
  };

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (isScrubbing) handleTimelineScrub(e);
    };
    const handleMouseUp = () => {
      if (isScrubbing) setIsScrubbing(false);
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

  // Safe array guards
  const safeTranscript = Array.isArray(transcript) ? transcript : [];
  const safeKeyframes = Array.isArray(keyframes) ? keyframes : [];
  const safeSelected = Array.isArray(selected) ? selected : [];
  const safeMapBTCKeyframes = Array.isArray(mapBTCKeyframes) ? mapBTCKeyframes : [];

  // Sample Keyframes for Timeline Strip
  const targetTimelineCount = 20;
  const sampledKeyframes = [];
  if (safeKeyframes.length > 0) {
    for (let i = 0; i < targetTimelineCount; i++) {
      const idx = Math.floor(
        (i / (targetTimelineCount - 1)) * (safeKeyframes.length - 1)
      );
      sampledKeyframes.push(safeKeyframes[idx]);
    }
  }

  const fps = frameInfo?.fps || 25;
  const duration = videoElementRef.current ? videoElementRef.current.duration : 0;
  const currentPercentage =
    duration > 0 ? (frameCounter / fps / duration) * 100 : 0;

  // Helper function to get available keyframes list sorted by timestamp
  const getNavKeyframeList = () => {
    const btcList = Array.isArray(mapBTCKeyframesRef.current) ? mapBTCKeyframesRef.current : [];
    if (btcList && btcList.length > 0) {
      return [...btcList].sort((a, b) => a.pts_time - b.pts_time);
    }
    const kfList = Array.isArray(keyframesRef.current) ? keyframesRef.current : [];
    if (kfList && kfList.length > 0) {
      return kfList
        .map((k) => {
          const idx = parseInt(k, 10);
          return isNaN(idx) ? null : { raw_idx: idx, pts_time: idx / fps };
        })
        .filter(Boolean)
        .sort((a, b) => a.pts_time - b.pts_time);
    }
    return [];
  };

  // Active Transcript Auto-Scroll
  useEffect(() => {
    if (safeTranscript.length === 0) return;
    const currentTime = frameCounter / fps;
    const activeIdx = safeTranscript.findIndex(
      (item) => item && currentTime >= item.start_time && currentTime <= item.end_time
    );
    if (activeIdx !== activeSegmentIndex) {
      setActiveSegmentIndex(activeIdx);
      if (activeIdx !== -1) {
        const activeEl = document.getElementById(`asr-seg-${activeIdx}`);
        if (activeEl && transcriptContainerRef.current) {
          activeEl.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }
    }
  }, [frameCounter, safeTranscript, activeSegmentIndex, fps]);

  // YouTube Hotkeys & Video Playback Controls
  useEffect(() => {
    const videoElement = videoElementRef.current;
    if (!videoElement) return;

    videoElement.currentTime =
      frameInfo.time || parseInt(frameInfo.frame_id, 10) / fps - 0.5;
    videoElement.focus();

    const handleKeyDown = (e) => {
      const isInInput = ["INPUT", "TEXTAREA", "SELECT"].includes(
        e.target.tagName
      );

      switch (e.keyCode) {
        case 27: // Escape - close video player (or exit fullscreen first)
          if (!document.fullscreenElement) {
            onCancel();
          }
          return;

        case 70: // F - Fullscreen Video + Diagram Container
          if (!isInInput) {
            e.preventDefault();
            toggleVideoFullscreen();
          }
          return;

        case 75: // K - Play/Pause
        case 32: // Space - Play/Pause
          if (!isInInput) {
            e.preventDefault();
            if (videoElement.paused) videoElement.play();
            else videoElement.pause();
          }
          return;

        case 37: // Left arrow - Seek Step back OR BTC keyframe if Ctrl OR frame by frame if Shift
          if (!isInInput) {
            e.preventDefault();
            if (e.ctrlKey || e.metaKey) {
              if (!videoElement.paused) videoElement.pause();
              const list = getNavKeyframeList();
              if (list && list.length > 0) {
                const curTime = videoElement.currentTime;
                const eps = Math.min(0.02, 0.5 / fps);
                const prevKf = [...list].reverse().find((item) => item.pts_time < curTime - eps);
                if (prevKf) {
                  videoElement.currentTime = Math.max(prevKf.pts_time, 0);
                } else {
                  videoElement.currentTime = 0;
                }
              } else {
                videoElement.currentTime = Math.max(
                  videoElement.currentTime - seekStepRef.current,
                  0
                );
              }
            } else if (e.shiftKey) {
              videoElement.currentTime = Math.max(
                videoElement.currentTime - 1 / fps,
                0
              );
            } else {
              videoElement.currentTime = Math.max(
                videoElement.currentTime - seekStepRef.current,
                0
              );
            }
          }
          return;

        case 39: // Right arrow - Seek Step forward OR BTC keyframe if Ctrl OR frame by frame if Shift
          if (!isInInput) {
            e.preventDefault();
            if (e.ctrlKey || e.metaKey) {
              if (!videoElement.paused) videoElement.pause();
              const list = getNavKeyframeList();
              if (list && list.length > 0) {
                const curTime = videoElement.currentTime;
                const eps = Math.min(0.02, 0.5 / fps);
                const nextKf = list.find((item) => item.pts_time > curTime + eps);
                if (nextKf) {
                  videoElement.currentTime = Math.min(nextKf.pts_time, videoElement.duration || Infinity);
                } else if (videoElement.duration) {
                  videoElement.currentTime = videoElement.duration;
                }
              } else {
                videoElement.currentTime = Math.min(
                  videoElement.currentTime + seekStepRef.current,
                  videoElement.duration
                );
              }
            } else if (e.shiftKey) {
              videoElement.currentTime = Math.min(
                videoElement.currentTime + 1 / fps,
                videoElement.duration
              );
            } else {
              videoElement.currentTime = Math.min(
                videoElement.currentTime + seekStepRef.current,
                videoElement.duration
              );
            }
          }
          return;

        case 219: // [ - Go 1 frame back
          if (!isInInput) {
            e.preventDefault();
            videoElement.currentTime = Math.max(
              videoElement.currentTime - 1 / fps,
              0
            );
          }
          return;

        case 221: // ] - Go 1 frame forward
          if (!isInInput) {
            e.preventDefault();
            videoElement.currentTime = Math.min(
              videoElement.currentTime + 1 / fps,
              videoElement.duration
            );
          }
          return;

        case 189: // - - Decrease playback speed
          if (!isInInput) {
            e.preventDefault();
            videoElement.playbackRate = Math.max(
              videoElement.playbackRate - 0.25,
              0.25
            );
          }
          return;

        case 187: // + - Increase playback speed
          if (!isInInput) {
            e.preventDefault();
            videoElement.playbackRate = Math.min(
              videoElement.playbackRate + 0.25,
              4
            );
          }
          return;

        case 83: // S - Toggle select frame
          if (!isInInput) {
            e.preventDefault();
            document.getElementById("toggle-select-frame-btn")?.click();
          }
          return;

        case 13: // Enter - Focus Answer Input or Submit Selected if Shift
          if (e.shiftKey) {
            e.preventDefault();
            document.getElementById("submit-selected-btn")?.click();
          } else if (!isInInput) {
            e.preventDefault();
            const ansInput = document.getElementById("answer-text-input");
            if (ansInput) ansInput.focus();
          }
          return;
      }
    };

    document.addEventListener("keydown", handleKeyDown, true);
    const id = setInterval(() => {
      if (videoElement) {
        setFrameCounter(videoElement.currentTime * fps);
      }
    }, 20);

    return () => {
      document.removeEventListener("keydown", handleKeyDown, true);
      clearInterval(id);
    };
  }, [fps, frameInfo, onCancel]);

  const curTime = videoElementRef.current ? videoElementRef.current.currentTime : (frameCounter / fps);

  // Precision snapping threshold (< 0.4 of a single frame duration)
  // Ensures keyframe IDs match when directly on keyframes, but releases immediately on single-frame stepping
  const snapThreshold = Math.min(0.015, 0.4 / fps);
  let activeFrameNum = Math.round(curTime * fps);
  if (safeMapBTCKeyframes.length > 0) {
    const matchedKf = safeMapBTCKeyframes.find((kf) => Math.abs(kf.pts_time - curTime) <= snapThreshold);
    if (matchedKf) {
      activeFrameNum = matchedKf.raw_idx;
    }
  } else if (safeKeyframes.length > 0) {
    const matchedRaw = safeKeyframes.find((k) => Math.abs(parseInt(k, 10) / fps - curTime) <= snapThreshold);
    if (matchedRaw !== undefined) {
      activeFrameNum = parseInt(matchedRaw, 10);
    }
  }

  const currentFrameStr = String(activeFrameNum).padStart(6, "0");
  const currentFrameId = `${frameInfo.video_id}#${currentFrameStr}`;
  const isFrameSelected = safeSelected.includes(currentFrameId);

  const selectedFramesOfThisVideo = safeSelected
    .filter((id) => id && id.startsWith(frameInfo.video_id + "#"))
    .map((id) => id.split("#")[1])
    .sort((a, b) => parseInt(a, 10) - parseInt(b, 10));

  const jumpToFrame = (frameNum) => {
    if (videoElementRef.current) {
      const parsedNum = parseInt(frameNum, 10);
      if (safeMapBTCKeyframes.length > 0) {
        const matchedKf = safeMapBTCKeyframes.find((kf) => kf.raw_idx === parsedNum);
        if (matchedKf) {
          videoElementRef.current.currentTime = matchedKf.pts_time;
          return;
        }
      }
      videoElementRef.current.currentTime = parsedNum / fps;
    }
  };

  return (
    <div
      onClick={(e) => {
        e.stopPropagation();
        onCancel();
      }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-75 p-2 overflow-auto"
    >
      <div
        className="bg-white rounded-xl flex flex-col shadow-2xl transition-all duration-200 border border-gray-300 p-3 w-[98vw] h-[92vh] max-h-[98vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Optimized Ultra-Compact Header Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2 pb-2 border-b border-gray-200 text-xs shrink-0">
          {/* Left: Metadata Badges & Frame Selection */}
          <div className="flex flex-wrap items-center gap-2 font-mono">
            {/* Video & Frame Info Badges */}
            <div className="flex items-center gap-1.5 bg-gray-100 border border-gray-300 px-2 py-1 rounded-lg shadow-sm">
              <span className="text-gray-500 font-sans text-[11px]">Video:</span>
              <strong className="text-blue-700">{frameInfo.video_id}</strong>
              <span className="text-gray-300">|</span>
              <span className="text-gray-500 font-sans text-[11px]">Frame:</span>
              <strong className="text-emerald-700">#{frameInfo.frame_id}</strong>
              <span className="text-gray-300">|</span>
              <span className="text-gray-500 font-sans text-[11px]">Pos:</span>
              <strong className="text-purple-700">#{currentFrameStr}</strong>
            </div>

            {/* Seek Step */}
            <div className="flex items-center gap-1 bg-white border border-gray-300 px-2 py-1 rounded-lg shadow-sm">
              <span className="text-gray-600 font-sans text-[11px]">Step(s):</span>
              <input
                type="number"
                min="1"
                max="60"
                value={seekStep}
                onChange={handleSeekStepChange}
                className="w-8 text-center text-xs font-bold border-b border-gray-300 focus:outline-none focus:border-blue-500 bg-transparent"
              />
            </div>

            {/* Select Frame Button */}
            <button
              id="toggle-select-frame-btn"
              onClick={() => {
                if (isFrameSelected) removeSelected(currentFrameId);
                else addSelected(currentFrameId);
              }}
              className={classNames(
                "px-2.5 py-1 text-xs font-bold rounded-lg border transition-all shadow-sm flex items-center gap-1",
                {
                  "bg-emerald-600 hover:bg-emerald-700 text-white border-emerald-700": isFrameSelected,
                  "bg-white hover:bg-gray-100 text-gray-800 border-gray-300": !isFrameSelected,
                }
              )}
            >
              {isFrameSelected ? "✓ Selected" : "+ Select Frame"}
            </button>

            {/* Fullscreen Video + Diagram Trigger Button */}
            <button
              type="button"
              onClick={toggleVideoFullscreen}
              className="px-2 py-1 text-xs font-bold rounded-lg border border-gray-300 bg-gray-100 hover:bg-gray-200 text-gray-800 transition-colors shadow-sm flex items-center gap-1"
              title="Fullscreen Video + Diagram (Hotkey: F)"
            >
              ⛶ Fullscreen (F)
            </button>

            {/* Saved in this video pills with remove (x) buttons */}
            {selectedFramesOfThisVideo.length > 0 && (
              <div className="flex items-center gap-1 border-l border-gray-300 pl-2 shrink min-w-0">
                <span className="text-[10px] text-gray-500 font-sans shrink-0">Saved:</span>
                <div className="flex items-center gap-1 max-w-[36rem] overflow-x-auto py-0.5 scrollbar-thin shrink whitespace-nowrap">
                  {selectedFramesOfThisVideo.map((frameNum) => {
                    const itemFullId = `${frameInfo.video_id}#${frameNum}`;
                    const isCurrent = frameNum === currentFrameStr;
                    return (
                      <span
                        key={frameNum}
                        onClick={() => jumpToFrame(frameNum)}
                        className={classNames(
                          "inline-flex items-center gap-1 text-[10px] pl-1.5 pr-1 py-0.5 rounded font-mono cursor-pointer border shadow-sm transition-all group shrink-0",
                          {
                            "bg-orange-500 border-orange-600 text-white font-bold": isCurrent,
                            "bg-white border-gray-300 text-gray-700 hover:bg-orange-50": !isCurrent,
                          }
                        )}
                        title="Click to jump to frame"
                      >
                        <span>#{frameNum}</span>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            removeSelected(itemFullId);
                          }}
                          className={classNames(
                            "w-3.5 h-3.5 rounded-full flex items-center justify-center text-[10px] font-bold transition-colors ml-0.5",
                            {
                              "text-white/80 hover:text-white hover:bg-orange-600": isCurrent,
                              "text-red-500 hover:text-white hover:bg-red-500": !isCurrent,
                            }
                          )}
                          title={`Remove ${itemFullId} from selected`}
                        >
                          ✕
                        </button>
                      </span>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Right: Quick Answer Submission & Close */}
          <div className="flex items-center gap-2">
            <fetcher.Form
              id="answer-form"
              onSubmit={(e) => {
                e.preventDefault();
                const formData = new FormData(e.currentTarget);
                const data = Object.fromEntries(formData);
                const newAnswer = {
                  ...data,
                  video_id: frameInfo.video_id,
                  frame_id: String(activeFrameNum),
                  frame_counter: activeFrameNum,
                  time: videoElementRef.current?.currentTime || 0,
                };
                if (submitAnswer) submitAnswer(newAnswer);
              }}
              className="flex items-center gap-1"
            >
              <div className="flex items-center border border-gray-300 rounded-lg overflow-hidden bg-white shadow-sm">
                <select
                  required
                  name="query_id"
                  value={selectedQueryId}
                  onChange={(e) => setSelectedQueryId(e.target.value)}
                  className="py-1 px-2 text-xs bg-gray-50 border-r border-gray-300 focus:outline-none font-bold"
                >
                  {displayEvaluationIds.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.name}
                    </option>
                  ))}
                </select>

                {selectedQueryId === "QA" && (
                  <input
                    type="text"
                    name="answer"
                    placeholder="Answer"
                    autoComplete="off"
                    className="py-1 px-2 text-xs focus:outline-none w-32 font-sans"
                  />
                )}

                <button
                  type="submit"
                  className="text-xs font-bold px-3 py-1 bg-sky-100 hover:bg-sky-200 active:bg-sky-300 border-l border-gray-300 text-sky-900 transition-colors"
                >
                  Submit
                </button>
              </div>
            </fetcher.Form>

            {/* Close Modal Button */}
            <button
              type="button"
              onClick={onCancel}
              className="p-1 px-2.5 bg-red-600 hover:bg-red-700 text-white font-bold text-xs rounded-lg shadow-sm"
              title="Close (Esc)"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Main Body: Video + CapCut Keyframe Timeline + Live Transcript */}
        <div className="flex flex-row gap-3 overflow-hidden flex-1 min-h-0 h-full">
          {/* Combined Video & CapCut Timeline Container (Will go Fullscreen together on key F!) */}
          <div
            ref={videoWrapperRef}
            className="flex flex-col flex-1 min-w-0 h-full max-h-full overflow-hidden justify-between bg-black p-1.5 rounded-lg shadow-md border border-gray-800"
          >
            <video
              ref={videoElementRef}
              id="playing-video"
              controls
              autoPlay
              className="w-full flex-1 min-h-0 max-h-[calc(100%-4.5rem)] object-contain bg-black rounded-lg"
            >
              <source src={frameInfo.video_uri} type="video/mp4" />
            </video>

            {/* CapCut Style Timeline Keyframe Diagram Strip (Gắn liền dưới Video cả ở chế độ Fullscreen!) */}
            <div
              ref={timelineRef}
              onMouseDown={handleMouseDown}
              className="mt-1.5 flex flex-row w-full py-0.5 items-center h-16 bg-gray-900 rounded border border-gray-700 overflow-hidden relative select-none cursor-ew-resize shadow-md shrink-0"
              title="CapCut Timeline Keyframe Strip - Click or drag to scrub video"
            >
              {/* Red Playhead Line */}
              {videoElementRef.current && (
                <div
                  style={{ left: `${currentPercentage}%` }}
                  className="absolute top-0 bottom-0 w-1 bg-red-600 z-20 pointer-events-none shadow-md shadow-red-500/80"
                />
              )}

              {sampledKeyframes.length === 0 ? (
                <div className="text-gray-400 text-xs text-center w-full py-4 pointer-events-none">
                  Loading timeline keyframes...
                </div>
              ) : (
                sampledKeyframes.map((kf, i) => (
                  <div
                    key={kf + "-" + i}
                    className="flex-1 h-14 relative group overflow-hidden pointer-events-none border-r border-gray-800"
                  >
                    <img
                      src={`http://127.0.0.1:6900/api/files/${frameInfo.video_id}/${kf}`}
                      alt={kf}
                      loading="lazy"
                      className="h-full w-full object-cover bg-black"
                    />
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Right: Live Transcript Sidebar (Expanded Comfortable Height Box) */}
          <div className="flex flex-col w-80 h-full max-h-full border border-gray-300 rounded-lg bg-gray-50 shadow-sm overflow-hidden shrink-0">
            <div className="flex justify-between items-center p-2 bg-white border-b border-gray-200 shrink-0">
              <span className="font-bold text-xs text-gray-800 flex items-center gap-1">
                <span>Live Transcript</span>
                {safeTranscript.length > 0 && (
                  <span className="text-[10px] text-gray-400 font-mono">({safeTranscript.length})</span>
                )}
              </span>
              <input
                type="text"
                placeholder="Search transcript..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="text-xs py-1 px-2 border border-gray-300 rounded focus:outline-none focus:border-blue-500 font-medium w-36"
              />
            </div>

            <div
              ref={transcriptContainerRef}
              className="flex-1 overflow-y-auto p-2 space-y-1.5"
            >
              {safeTranscript.length === 0 ? (
                <div className="text-gray-400 text-center py-8 text-xs italic">
                  No transcript available
                </div>
              ) : (
                safeTranscript.map((item, idx) => {
                  const currentTime = frameCounter / fps;
                  const isActive =
                    currentTime >= item.start_time &&
                    currentTime <= item.end_time;
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
                        "p-2 rounded border-l-4 cursor-pointer transition-all text-xs shadow-sm",
                        {
                          "bg-blue-100 border-l-blue-600 font-bold text-blue-950":
                            isActive,
                          "bg-yellow-100 border-l-yellow-500 text-gray-900":
                            matchesSearch && !isActive,
                          "bg-white border-l-transparent text-gray-700 hover:bg-gray-100":
                            !isActive && !matchesSearch,
                        }
                      )}
                    >
                      <div className="flex justify-between text-[10px] text-gray-400 mb-0.5 font-mono">
                        <span>
                          {formatTime(item.start_time)} - {formatTime(item.end_time)}
                        </span>
                        <span>Frame {item.start_frame}</span>
                      </div>
                      <div className="leading-relaxed break-words">
                        {item.text}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
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
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}.${ms}`;
}
