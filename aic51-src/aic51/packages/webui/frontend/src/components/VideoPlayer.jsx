import { useFetcher } from "react-router-dom";
import { createContext, useEffect, useContext, useState, useRef } from "react";
import classNames from "classnames";
import { AuthContext } from "./AuthProvider.jsx";
import { useSelected } from "./SelectedProvider.jsx";
import { getFrameInfo, getVideoTranscript, getVideoThumbnails, getVideoKeyframes, getVideoMapKeyframes } from "../services/search.js";
import {
  DEFAULT_DRES_URL,
  DRES_SERVER_KEY,
  DRES_SESSION_KEY,
  DRES_EVAL_KEY,
  cleanVideoId,
  formatDresTime,
  parseSecondsFromDres,
  parseTimeToSeconds,
  resolveTimeFromFrame,
  submitDresAnswer,
  getLiveEvaluationContext,
  buildPayload,
  parseDresError,
  addSubmissionHistoryEntry,
} from "../services/dres.js";

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
  const [thumbnails, setThumbnails] = useState([]);

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

  // Load Thumbnails Timeline Strip
  useEffect(() => {
    if (!frameInfo?.video_id) return;
    getVideoThumbnails(frameInfo.video_id)
      .then((res) => {
        const list = Array.isArray(res) ? res : (res?.thumbnails || res?.keyframes || []);
        setThumbnails(list);
      })
      .catch(() => setThumbnails([]));
  }, [frameInfo?.video_id]);

  const thumbnailsRef = useRef([]);
  useEffect(() => {
    thumbnailsRef.current = thumbnails;
  }, [thumbnails]);

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
  const safeThumbnails = Array.isArray(thumbnails) ? thumbnails : [];
  const safeSelected = Array.isArray(selected) ? selected : [];
  const safeMapBTCKeyframes = Array.isArray(mapBTCKeyframes) ? mapBTCKeyframes : [];

  // Source list for Timeline Strip (prioritize thumbnails, fallback to map-keyframes)
  const timelineFrames = safeThumbnails.length > 0
    ? safeThumbnails
    : safeMapBTCKeyframes.map((k) => k.frame_idx || String(k.raw_idx).padStart(6, "0"));

  // Sample Thumbnails for Timeline Strip
  const targetTimelineCount = 20;
  const sampledThumbnails = [];
  if (timelineFrames.length > 0) {
    if (timelineFrames.length <= targetTimelineCount) {
      sampledThumbnails.push(...timelineFrames);
    } else {
      for (let i = 0; i < targetTimelineCount; i++) {
        const idx = Math.floor(
          (i / (targetTimelineCount - 1)) * (timelineFrames.length - 1)
        );
        sampledThumbnails.push(timelineFrames[idx]);
      }
    }
  }

  const fps = frameInfo?.fps || 25;
  const duration = videoElementRef.current ? videoElementRef.current.duration : 0;
  const currentPercentage =
    duration > 0 ? (frameCounter / fps / duration) * 100 : 0;

  // Helper function to get available keyframes/thumbnails list sorted by timestamp
  const getNavKeyframeList = () => {
    const btcList = Array.isArray(mapBTCKeyframesRef.current) ? mapBTCKeyframesRef.current : [];
    if (btcList && btcList.length > 0) {
      return [...btcList].sort((a, b) => a.pts_time - b.pts_time);
    }
    const thumbList = Array.isArray(thumbnailsRef.current) ? thumbnailsRef.current : [];
    if (thumbList && thumbList.length > 0) {
      return thumbList
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

    const targetSeek = Math.max(0, (frameInfo.time || parseInt(frameInfo.frame_id, 10) / fps) - 0.5);
    const doSeek = () => {
      try {
        videoElement.currentTime = targetSeek;
      } catch (err) {}
    };

    if (videoElement.readyState >= 1) {
      doSeek();
    } else {
      videoElement.addEventListener("loadedmetadata", doSeek, { once: true });
    }
    videoElement.focus();

    const handleKeyDown = (e) => {
      const isInInput = ["INPUT", "TEXTAREA", "SELECT"].includes(
        e.target.tagName
      );

      switch (e.keyCode) {
        case 27: // Escape closes the DRES popup before the video player.
          if (showDresModalRef.current) {
            showDresModalRef.current = false;
            setShowDresModal(false);
            e.preventDefault();
            e.stopPropagation();
            return;
          }
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

        case 71: // G - Focus Go To input
          if (!isInInput) {
            e.preventDefault();
            document.getElementById("goto-input")?.focus();
          }
          return;

        case 83: // S - Toggle select frame, or Shift+S for Quick DRES Submit
          if (e.shiftKey) {
            e.preventDefault();
            handleOpenDresModal();
          } else if (!isInInput) {
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
  } else if (safeThumbnails.length > 0) {
    const matchedRaw = safeThumbnails.find((k) => Math.abs(parseInt(k, 10) / fps - curTime) <= snapThreshold);
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

  // Go To State (Frame or Time)
  const [goToMode, setGoToMode] = useState("frame"); // 'frame' | 'time'
  const [goToInput, setGoToInput] = useState("");

  const handleGoTo = (e) => {
    if (e) e.preventDefault();
    if (!goToInput.trim() || !videoElementRef.current) return;

    if (goToMode === "frame") {
      jumpToFrame(goToInput.trim());
    } else {
      const targetSec = parseTimeToSeconds(goToInput.trim());
      const maxDuration = videoElementRef.current.duration || 999999;
      videoElementRef.current.currentTime = Math.max(0, Math.min(targetSec, maxDuration));
    }
    setGoToInput("");
  };

  // Default standard AIC tasks presets
  const DEFAULT_AIC_TASKS = [
    { id: "tkis-test", name: "tkis-test", label: "tkis-test (Textual KIS)", type: "KIS" },
    { id: "vkis-test", name: "vkis-test", label: "vkis-test (Visual KIS)", type: "KIS" },
    { id: "qa-test", name: "qa-test", label: "qa-test (Question Answering)", type: "QA" },
    { id: "trake-test", name: "trake-test", label: "trake-test (TRAKE)", type: "TRAKE" },
    { id: "tkis-01", name: "tkis-01", label: "tkis-01 (Textual KIS 1)", type: "KIS" },
    { id: "tkis-02", name: "tkis-02", label: "tkis-02 (Textual KIS 2)", type: "KIS" },
    { id: "tkis-03", name: "tkis-03", label: "tkis-03 (Textual KIS 3)", type: "KIS" },
    { id: "tkis-04", name: "tkis-04", label: "tkis-04 (Textual KIS 4)", type: "KIS" },
    { id: "tkis-05", name: "tkis-05", label: "tkis-05 (Textual KIS 5)", type: "KIS" },
    { id: "vkis-01", name: "vkis-01", label: "vkis-01 (Visual KIS 1)", type: "KIS" },
    { id: "vkis-02", name: "vkis-02", label: "vkis-02 (Visual KIS 2)", type: "KIS" },
    { id: "vkis-03", name: "vkis-03", label: "vkis-03 (Visual KIS 3)", type: "KIS" },
    { id: "qa-01", name: "qa-01", label: "qa-01 (Q&A 1)", type: "QA" },
    { id: "qa-02", name: "qa-02", label: "qa-02 (Q&A 2)", type: "QA" },
    { id: "qa-03", name: "qa-03", label: "qa-03 (Q&A 3)", type: "QA" },
    { id: "trake-01", name: "trake-01", label: "trake-01 (TRAKE 1)", type: "TRAKE" },
    { id: "trake-02", name: "trake-02", label: "trake-02 (TRAKE 2)", type: "TRAKE" },
  ];

  // Quick DRES Submit State from Video Player
  const [showDresModal, setShowDresModal] = useState(false);
  showDresModalRef.current = showDresModal;
  const [dresActiveTask, setDresActiveTask] = useState(null);
  const [dresTaskRemainingSec, setDresTaskRemainingSec] = useState(null);
  const [dresIsRefreshing, setDresIsRefreshing] = useState(false);
  const [dresSelectedTaskName, setDresSelectedTaskName] = useState("tkis-test");
  const [dresAvailableTasks, setDresAvailableTasks] = useState(DEFAULT_AIC_TASKS);
  const [dresCustomTaskMode, setDresCustomTaskMode] = useState(false);
  const [dresCustomTaskName, setDresCustomTaskName] = useState("");
  const [dresTaskType, setDresTaskType] = useState(selectedQueryId || "KIS");
  const [dresAnswerText, setDresAnswerText] = useState("");
  const [dresFramesInput, setDresFramesInput] = useState("");
  const [dresExactTimeMs, setDresExactTimeMs] = useState(0);
  const [dresTimeSource, setDresTimeSource] = useState("");
  const [dresIsSubmitting, setDresIsSubmitting] = useState(false);
  const [dresResult, setDresResult] = useState(null);
  const [dresDryRun, setDresDryRun] = useState(false);
  const [dresCopiedJson, setDresCopiedJson] = useState(false);

  // Countdown Interval for remaining time in modal
  const dresCountdownRef = useRef(null);
  useEffect(() => {
    if (dresTaskRemainingSec !== null && dresTaskRemainingSec > 0) {
      if (!dresCountdownRef.current) dresCountdownRef.current = setInterval(() => {
        setDresTaskRemainingSec((prev) => {
          if (prev === null || prev <= 1) {
            clearInterval(dresCountdownRef.current);
            dresCountdownRef.current = null;
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    } else if (dresCountdownRef.current) {
      clearInterval(dresCountdownRef.current);
      dresCountdownRef.current = null;
    }
    return () => {
      if (dresCountdownRef.current) {
        clearInterval(dresCountdownRef.current);
        dresCountdownRef.current = null;
      }
    };
  }, [dresTaskRemainingSec > 0]);

  // Refresh live task info and timer from server
  const refreshLiveTaskInfo = async (silent = false) => {
    const sId = localStorage.getItem(DRES_SESSION_KEY);
    const eId = localStorage.getItem(DRES_EVAL_KEY);
    const sUrl = localStorage.getItem(DRES_SERVER_KEY) || DEFAULT_DRES_URL;

    if (!eId || !sId) return;
    if (!silent) setDresIsRefreshing(true);

    try {
      const context = await getLiveEvaluationContext(eId, sId, sUrl);
      if (localStorage.getItem(DRES_EVAL_KEY) !== eId) return;
      if (context.task) {
        setDresActiveTask(context.task);
        const taskName = context.task.name || "tkis-test";
        setDresSelectedTaskName(taskName);

        // Auto switch tab (KIS, QA, TRAKE)
        if (!silent) {
          const grp = String(context.task.taskGroup || context.task.taskType || taskName).toUpperCase();
          if (grp.includes("QA")) setDresTaskType("QA");
          else if (grp.includes("TRAKE") || grp.includes("TR-")) setDresTaskType("TRAKE");
          else setDresTaskType("KIS");
        }
      }
      const sec = parseSecondsFromDres(context.state?.timeLeft ?? context.task?.duration);
      setDresTaskRemainingSec((prev) => sec === null ? null : prev === null || Math.abs(prev - sec) > 2 ? sec : prev);

      if (context.taskTemplates.length > 0) {
          const loaded = context.taskTemplates.map((t) => ({
            id: t.id || t.name,
            name: t.name,
            label: `${t.name} (${t.taskGroup || t.taskType || "Task"})`,
            type: String(t.taskGroup || t.taskType || "").toUpperCase().includes("QA")
              ? "QA"
              : String(t.taskGroup || t.taskType || "").toUpperCase().includes("TRAKE")
              ? "TRAKE"
              : "KIS",
          }));
          setDresAvailableTasks(() => {
            const merged = [...loaded];
            DEFAULT_AIC_TASKS.forEach((def) => {
              if (!merged.some((m) => m.name === def.name)) merged.push(def);
            });
            return merged;
          });
      }
    } catch (err) {
      console.warn("Failed to refresh live task info:", err);
    } finally {
      if (!silent) setDresIsRefreshing(false);
    }
  };

  useEffect(() => {
    if (localStorage.getItem(DRES_SESSION_KEY)) refreshLiveTaskInfo(true);
    const poll = setInterval(() => refreshLiveTaskInfo(true), 8000);
    const onEvaluationChange = () => refreshLiveTaskInfo(true);
    const onStorage = (event) => {
      if ([DRES_EVAL_KEY, DRES_SESSION_KEY, DRES_SERVER_KEY].includes(event.key)) refreshLiveTaskInfo(true);
    };
    window.addEventListener("dres_eval_changed", onEvaluationChange);
    window.addEventListener("storage", onStorage);
    return () => {
      clearInterval(poll);
      window.removeEventListener("dres_eval_changed", onEvaluationChange);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const handleSelectTask = (taskName) => {
    if (taskName === "__CUSTOM__") {
      setDresCustomTaskMode(true);
      return;
    }
    setDresCustomTaskMode(false);
    setDresSelectedTaskName(taskName);

    const found = dresAvailableTasks.find((t) => t.name === taskName);
    if (found && found.type) {
      setDresTaskType(found.type);
    } else {
      const upper = String(taskName).toUpperCase();
      if (upper.includes("QA")) setDresTaskType("QA");
      else if (upper.includes("TRAKE") || upper.includes("TR-")) setDresTaskType("TRAKE");
      else setDresTaskType("KIS");
    }
  };

  const handleOpenDresModal = async () => {
    if (videoElementRef.current && !videoElementRef.current.paused) {
      videoElementRef.current.pause();
    }
    const cleanVid = cleanVideoId(frameInfo.video_id);
    const resolved = await resolveTimeFromFrame(
      cleanVid,
      activeFrameNum,
      videoElementRef.current?.currentTime,
      fps
    );
    setDresExactTimeMs(resolved.time_ms);
    setDresTimeSource(
      resolved.source.includes("map-keyframes")
        ? `map-keyframes (pts: ${resolved.pts_time.toFixed(3)}s, ${resolved.fps}fps)`
        : `tính từ fps ${resolved.fps}`
    );

    setDresResult(null);
    setDresCopiedJson(false);
    setDresFramesInput(String(activeFrameNum));
    setShowDresModal(true);

    // Refresh live task info and sync timer
    refreshLiveTaskInfo();
  };

  const getQuickDresBuiltPayload = () => {
    const cleanVid = cleanVideoId(frameInfo?.video_id);
    return buildPayload(dresTaskType, {
      videoId: cleanVid,
      startMs: dresExactTimeMs,
      endMs: dresExactTimeMs,
      answerText: dresAnswerText,
      framesList: dresFramesInput,
    });
  };

  const handleQuickDresSubmit = async (forceRealSubmit = false, forceDryRun = false) => {
    const sId = localStorage.getItem(DRES_SESSION_KEY);
    const eId = localStorage.getItem(DRES_EVAL_KEY);
    const sUrl = localStorage.getItem(DRES_SERVER_KEY) || DEFAULT_DRES_URL;

    const runAsDryRun = forceDryRun || (dresDryRun && !forceRealSubmit);

    if (!runAsDryRun && (!sId || !eId)) {
      alert("Chưa có Session ID hoặc Evaluation ID! Vui lòng cấu hình ở bảng DRES trên sidebar.");
      return;
    }

    const cleanVid = cleanVideoId(frameInfo.video_id);
    const built = getQuickDresBuiltPayload();

    setDresIsSubmitting(true);

    if (runAsDryRun) {
      setTimeout(() => {
        setDresIsSubmitting(false);
        setDresResult({
          status: "dry_run",
          title: "DRY-RUN THÀNH CÔNG (GIẢ LẬP)",
          message: "Format JSON payload hợp lệ 100%! Bạn có thể bấm 'Xác nhận nộp thật' bên dưới.",
        });
        addSubmissionHistoryEntry({
          task: dresSelectedTaskName,
          type: built.type,
          video: cleanVid,
          details: built.formattedText,
          verdict: "DRY-RUN",
          note: "Quick submit from player",
        });
      }, 300);
      return;
    }

    try {
      const res = await submitDresAnswer(eId, sId, built.payload, sUrl);
      if (res.ok) {
        const isCorrect = res.data && res.data.submission === "CORRECT";
        const isWrong = res.data && res.data.submission === "WRONG";
        setDresResult({
          status: isCorrect ? "success" : isWrong ? "wrong" : "pending",
          title: `KẾT QUẢ: ${res.data.submission || "OK"}`,
          message: res.data.description || (isCorrect ? "Chính xác! Điểm đã được ghi nhận." : "Sai - Bị trừ 10 điểm!"),
        });

        addSubmissionHistoryEntry({
          task: dresSelectedTaskName,
          type: built.type,
          video: cleanVid,
          details: built.formattedText,
          verdict: res.data.submission || "SUCCESS",
          note: res.data.description || "",
        });
      } else {
        const errMsg = parseDresError(res);
        setDresResult({
          status: "error",
          title: `LỖI TỪ SERVER (${res.status})`,
          message: errMsg,
          rawDescription: res.data?.description,
        });
      }
    } catch (err) {
      setDresResult({
        status: "error",
        title: "LỖI KẾT NỐI",
        message: err.message,
      });
    } finally {
      setDresIsSubmitting(false);
    }
  };

  return (
    <div
      onClick={(e) => {
        e.stopPropagation();
        if (showDresModalRef.current) setShowDresModal(false);
        else onCancel();
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

            {/* Go To Control (Frame or Time) */}
            <form
              onSubmit={handleGoTo}
              className="flex items-center gap-1 bg-white border border-gray-300 px-1.5 py-0.5 rounded-lg shadow-sm"
            >
              <button
                type="button"
                onClick={() => setGoToMode(goToMode === "frame" ? "time" : "frame")}
                className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-gray-100 hover:bg-gray-200 text-gray-700 border border-gray-300 select-none cursor-pointer"
                title="Click để chuyển giữa chế độ Frame hoặc Giây (Time)"
              >
                {goToMode === "frame" ? "🎬 Frame" : "⏱️ Time (s)"}
              </button>
              <input
                id="goto-input"
                type="text"
                placeholder={goToMode === "frame" ? "Nhập frame (G)..." : "Giây / MM:SS (G)..."}
                value={goToInput}
                onChange={(e) => setGoToInput(e.target.value)}
                className="w-24 text-xs font-mono font-semibold px-1 py-0.5 focus:outline-none bg-transparent"
              />
              <button
                type="submit"
                className="text-[10px] font-bold px-2 py-0.5 bg-blue-600 hover:bg-blue-700 text-white rounded shadow-xs cursor-pointer"
              >
                Go
              </button>
            </form>

            {/* Direct DRES Submit from Video Player */}
            <button
              type="button"
              onClick={handleOpenDresModal}
              className="px-2.5 py-1 text-xs font-bold rounded-lg bg-gradient-to-r from-sky-600 to-blue-700 hover:from-sky-500 hover:to-blue-600 text-white shadow-sm flex items-center gap-1 transition-all select-none cursor-pointer"
              title="Nộp trực tiếp frame hiện tại lên máy chủ DRES (Phím tắt: Shift + S)"
            >
              <span>⚡ Submit DRES</span>
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
              preload="metadata"
              className="w-full flex-1 min-h-0 max-h-[calc(100%-4.5rem)] object-contain bg-black rounded-lg"
            >
              <source src={frameInfo.video_uri} type="video/mp4" />
            </video>

            {/* CapCut Style Timeline Thumbnail Diagram Strip (Gắn liền dưới Video cả ở chế độ Fullscreen!) */}
            <div
              ref={timelineRef}
              onMouseDown={handleMouseDown}
              className="mt-1.5 flex flex-row w-full py-0.5 items-center h-16 bg-gray-900 rounded border border-gray-700 overflow-hidden relative select-none cursor-ew-resize shadow-md shrink-0"
              title="CapCut Timeline Thumbnail Strip - Click or drag to scrub video"
            >
              {/* Red Playhead Line */}
              {videoElementRef.current && (
                <div
                  style={{ left: `${currentPercentage}%` }}
                  className="absolute top-0 bottom-0 w-1 bg-red-600 z-20 pointer-events-none shadow-md shadow-red-500/80"
                />
              )}

              {sampledThumbnails.length === 0 ? (
                <div className="text-gray-400 text-xs text-center w-full py-4 pointer-events-none">
                  Loading timeline thumbnails...
                </div>
              ) : (
                sampledThumbnails.map((thumb, i) => (
                  <div
                    key={thumb + "-" + i}
                    className="flex-1 h-14 relative group overflow-hidden pointer-events-none border-r border-gray-800"
                  >
                    <img
                      src={`/api/files/${frameInfo.video_id}/${thumb}`}
                      onError={(e) => {
                        if (!e.target.dataset.triedFallback) {
                          e.target.dataset.triedFallback = "true";
                          e.target.src = `http://127.0.0.1:6900/api/files/${frameInfo.video_id}/${thumb}`;
                        }
                      }}
                      alt={thumb}
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

        {/* Quick DRES Submission Modal from Video Player (Màu trắng đồng bộ) */}
        {showDresModal && (() => {
          const quickPayload = getQuickDresBuiltPayload();
          const savedFrames = selected
            .filter((item) => typeof item === "string" && item.includes("#") && cleanVideoId(item.split("#")[0]) === cleanVideoId(frameInfo.video_id))
            .map((item) => item.split("#")[1]);
          return (
            <div
              onClick={(e) => {
                e.stopPropagation();
                setShowDresModal(false);
              }}
              className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-2xs flex items-center justify-center p-4 animate-fadeIn"
            >
              <div onClick={(e) => e.stopPropagation()} className="bg-white border border-gray-300 rounded-xl max-w-lg w-full max-h-[90vh] shadow-2xl flex flex-col text-gray-800 text-xs overflow-hidden">
                {/* Header */}
                <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 shrink-0">
                  <div className="flex items-center gap-1.5 font-bold text-blue-700 text-sm">
                    <span>⚡</span>
                    <span>NỘP BÀI DRES TỪ CURRENT FRAME</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowDresModal(false)}
                    className="text-gray-400 hover:text-gray-700 font-bold text-sm px-1.5 cursor-pointer"
                  >
                    ✕
                  </button>
                </div>

                <div className="flex flex-col gap-3 px-4 py-3 overflow-y-auto flex-1 min-h-0">

                {/* Active Task & Selection Bar with Refresh & Countdown Timer */}
                <div className="bg-blue-50/80 border border-blue-200 p-2.5 rounded-lg flex flex-col gap-2 text-blue-900 shadow-2xs">
                  {/* Row 1: Dropdown chọn câu & Nút Làm mới */}
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 flex-1 min-w-0">
                      <span className="font-bold text-[11px] shrink-0 text-blue-800 flex items-center gap-1">
                        <span className="inline-block w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.8)]"></span>
                        Đang thi:
                      </span>

                      {!dresCustomTaskMode ? (
                        <select
                          value={dresSelectedTaskName}
                          onChange={(e) => handleSelectTask(e.target.value)}
                          className="flex-1 bg-white border border-blue-300 rounded px-2 py-1 text-[11px] font-bold text-blue-950 focus:outline-none focus:border-blue-500 shadow-2xs cursor-pointer truncate"
                          title="Chọn câu thi trên hệ thống DRES"
                        >
                          {dresActiveTask && !dresAvailableTasks.some((t) => t.name === dresActiveTask.name) && (
                            <option value={dresActiveTask.name}>
                              ⭐ {dresActiveTask.name} (Đang diễn ra trên DRES)
                            </option>
                          )}
                          {dresAvailableTasks.map((task) => (
                            <option key={task.id || task.name} value={task.name}>
                              {dresActiveTask && dresActiveTask.name === task.name ? "⭐ " : ""}{task.label || task.name}
                            </option>
                          ))}
                          <option value="__CUSTOM__">✏️ Nhập câu khác...</option>
                        </select>
                      ) : (
                        <div className="flex items-center gap-1 flex-1 min-w-0">
                          <input
                            type="text"
                            placeholder="Nhập tên câu (vd: tkis-06, qa-04)..."
                            value={dresCustomTaskName}
                            onChange={(e) => {
                              const val = e.target.value;
                              setDresCustomTaskName(val);
                              setDresSelectedTaskName(val);
                              const upper = String(val).toUpperCase();
                              if (upper.includes("QA")) setDresTaskType("QA");
                              else if (upper.includes("TRAKE") || upper.includes("TR-")) setDresTaskType("TRAKE");
                              else setDresTaskType("KIS");
                            }}
                            autoFocus
                            className="flex-1 bg-white border border-blue-400 rounded px-2 py-1 text-[11px] font-bold text-blue-950 focus:outline-none shadow-2xs truncate"
                          />
                          <button
                            type="button"
                            onClick={() => {
                              setDresCustomTaskMode(false);
                              if (!dresCustomTaskName.trim()) {
                                setDresSelectedTaskName(dresActiveTask?.name || "tkis-test");
                              }
                            }}
                            className="px-1.5 py-1 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded text-[10px] font-bold shrink-0 cursor-pointer"
                            title="Quay lại danh sách câu có sẵn"
                          >
                            ✕ Huỷ
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Nút Làm mới */}
                    <button
                      type="button"
                      onClick={() => refreshLiveTaskInfo()}
                      disabled={dresIsRefreshing}
                      className="px-2.5 py-1 bg-white hover:bg-blue-100 active:bg-blue-200 text-blue-700 border border-blue-300 rounded font-bold text-[11px] flex items-center gap-1 transition-colors cursor-pointer shadow-2xs shrink-0 disabled:opacity-60"
                      title="Bấm để đồng bộ câu thi và thời gian từ máy chủ DRES"
                    >
                      <span className={dresIsRefreshing ? "animate-spin" : ""}>🔄</span>
                      <span>{dresIsRefreshing ? "Đang tải..." : "Làm mới"}</span>
                    </button>
                  </div>

                  {/* Row 2: Status & Time Display */}
                  <div className="flex items-center justify-between text-[11px] border-t border-blue-200/60 pt-1.5">
                    <div className="flex items-center gap-1.5 truncate">
                      <span className="text-gray-600 font-mono text-[10px]">
                        Mục tiêu: <strong className="text-blue-900">{dresSelectedTaskName}</strong>
                      </span>
                      {dresActiveTask && (
                        <span className="text-[10px] bg-blue-100 text-blue-800 font-semibold px-1.5 py-0.2 rounded border border-blue-200 shrink-0">
                          {dresActiveTask.taskGroup || dresActiveTask.taskType || "KIS"}
                        </span>
                      )}
                    </div>

                    {/* Countdown Timer Badge */}
                    <div className="flex items-center gap-1.5 shrink-0">
                      <span className="text-gray-500 text-[10px]">Thời gian:</span>
                      {dresTaskRemainingSec !== null ? (
                        dresTaskRemainingSec > 60 ? (
                          <span className="px-2 py-0.5 rounded text-[11px] font-extrabold font-mono bg-emerald-100 text-emerald-800 border border-emerald-300 shadow-2xs">
                             ⏱️ {formatDresTime(dresTaskRemainingSec)}
                          </span>
                        ) : dresTaskRemainingSec > 0 ? (
                          <span className="px-2 py-0.5 rounded text-[11px] font-extrabold font-mono bg-rose-100 text-rose-800 border border-rose-300 shadow-2xs animate-pulse">
                             ⏱️ {formatDresTime(dresTaskRemainingSec)}
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded text-[11px] font-extrabold font-mono bg-gray-200 text-gray-700 border border-gray-300">
                            ⏱️ Hết giờ (00:00)
                          </span>
                        )
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-blue-100 text-blue-700 border border-blue-200">
                          ⏱️ --:--
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Warning Banner */}
                {dresDryRun ? (
                  <div className="bg-amber-50 border border-amber-300 p-2.5 rounded-lg text-amber-900 text-[11px] leading-relaxed">
                    <strong>CHẾ ĐỘ DRY-RUN:</strong> Hệ thống sẽ tạo và kiểm tra cấu trúc JSON chuẩn trước. Bạn có thể xem trước JSON bên dưới và quyết định nộp thật!
                  </div>
                ) : (
                  <div className="bg-rose-50 border border-rose-300 p-2.5 rounded-lg text-rose-900 text-[11px] leading-relaxed">
                    <strong>⚠️ CẢNH BÁO PHẠT ĐIỂM:</strong> Nộp sai trước lần đúng đầu tiên sẽ bị <strong>trừ 10 điểm</strong>! Vui lòng kiểm tra kỹ trước khi bấm nộp.
                  </div>
                )}

                {/* Video & Time Info Card */}
                <div className="bg-gray-50 p-2.5 rounded-lg border border-gray-200 flex flex-col gap-1 font-mono text-[11px]">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Video ID:</span>
                    <strong className="text-blue-700">{cleanVideoId(frameInfo.video_id)}</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Current Frame:</span>
                    <strong className="text-emerald-700">#{activeFrameNum}</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Thời gian quy đổi:</span>
                    <strong className="text-purple-700">
                      {dresExactTimeMs.toLocaleString()} ms ({dresTimeSource})
                    </strong>
                  </div>
                </div>

                {/* Task Type Switcher */}
                <div className="flex items-center gap-1.5">
                  <label className="text-gray-700 text-[11px] font-bold">Loại Task:</label>
                  <div className="flex gap-1 flex-1">
                    {["KIS", "QA", "TRAKE"].map((t) => (
                      <button
                        key={t}
                        type="button"
                        onClick={() => setDresTaskType(t)}
                        className={`flex-1 py-1 rounded font-bold text-[11px] transition-colors cursor-pointer border ${
                          dresTaskType === t
                            ? "bg-blue-600 text-white border-blue-700 shadow-2xs"
                            : "bg-gray-100 text-gray-700 border-gray-200 hover:bg-gray-200"
                        }`}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </div>

                {/* QA Answer Input if QA */}
                {dresTaskType === "QA" && (
                  <div className="flex flex-col gap-1">
                    <label className="text-gray-700 text-[11px] font-bold">Câu trả lời (QA Answer):</label>
                    <input
                      type="text"
                      placeholder="Ví dụ: red car, blue bus, 42..."
                      value={dresAnswerText}
                      onChange={(e) => setDresAnswerText(e.target.value)}
                      autoFocus
                      className="w-full bg-white border border-gray-300 rounded px-2 py-1.5 text-gray-900 font-semibold text-xs focus:border-blue-500 focus:outline-none shadow-2xs"
                    />
                    <div className="font-mono text-[10px] text-emerald-700 truncate bg-emerald-50 p-1.5 rounded border border-emerald-200">
                      Chuỗi: QA-{dresAnswerText || "<ANS>"}-{cleanVideoId(frameInfo.video_id)}-{dresExactTimeMs}
                    </div>
                  </div>
                )}

                {/* TRAKE Info if TRAKE */}
                {dresTaskType === "TRAKE" && (
                  <div className="flex flex-col gap-1.5">
                    <input
                      type="text"
                      value={dresFramesInput}
                      onChange={(e) => setDresFramesInput(e.target.value)}
                      placeholder="Frame IDs, cách nhau bằng dấu phẩy"
                      className="w-full bg-white border border-gray-300 rounded px-2 py-1.5 font-mono text-xs"
                    />
                    <div className="flex flex-wrap gap-1.5">
                      <button type="button" onClick={() => setDresFramesInput((prev) => [...prev.split(/[,;\s]+/).filter(Boolean), String(activeFrameNum)].join(","))} className="px-2 py-1 rounded bg-blue-100 text-blue-800 font-bold">
                        + Thêm #{activeFrameNum}
                      </button>
                      <button type="button" onClick={() => setDresFramesInput(savedFrames.join(","))} className="px-2 py-1 rounded bg-blue-100 text-blue-800 font-bold">
                        📋 Lấy {savedFrames.length} frame đã lưu
                      </button>
                    </div>
                    <div className="font-mono text-[10px] text-emerald-700 break-all bg-emerald-50 p-1.5 rounded border border-emerald-200">
                      Chuỗi: {quickPayload.formattedText}
                    </div>
                  </div>
                )}

                {/* Live JSON Payload Box */}
                <div className="flex flex-col gap-1">
                  <div className="flex items-center justify-between text-[11px] font-semibold text-gray-600">
                    <span>Cấu trúc JSON Payload gửi đi:</span>
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(JSON.stringify(quickPayload.payload, null, 2));
                        setDresCopiedJson(true);
                        setTimeout(() => setDresCopiedJson(false), 2000);
                      }}
                      className="text-blue-600 hover:text-blue-800 text-[10px] font-bold flex items-center gap-1 cursor-pointer"
                    >
                      {dresCopiedJson ? "✓ Đã chép!" : "📋 Sao chép JSON"}
                    </button>
                  </div>
                  <div className="bg-gray-50 border border-gray-300 p-2 rounded-lg font-mono text-[11px] text-gray-900 max-h-28 overflow-y-auto shadow-inner">
                    <pre>{JSON.stringify(quickPayload.payload, null, 2)}</pre>
                  </div>
                </div>

                {/* Dry-Run Checkbox Option */}
                <div className="flex items-center justify-between pt-0.5">
                  <label className="flex items-center gap-1.5 cursor-pointer text-[11px] text-amber-800 font-semibold select-none">
                    <input
                      type="checkbox"
                      checked={dresDryRun}
                      onChange={(e) => setDresDryRun(e.target.checked)}
                      className="rounded text-amber-600 focus:ring-0 cursor-pointer"
                    />
                    <span>Chạy thử giả lập (Dry-Run)</span>
                  </label>
                </div>

                {/* Live Result if any */}
                {dresResult && (
                  <div
                    className={`p-2.5 rounded-lg border text-xs font-semibold flex flex-col gap-1 shadow-2xs ${
                      dresResult.status === "success"
                        ? "bg-emerald-50 border-emerald-300 text-emerald-900"
                        : dresResult.status === "wrong"
                        ? "bg-rose-50 border-rose-300 text-rose-900"
                        : dresResult.status === "dry_run"
                        ? "bg-sky-50 border-sky-300 text-sky-900"
                        : "bg-rose-50 border-rose-400 text-rose-900"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span>{dresResult.title}</span>
                      {dresResult.status === "dry_run" && (
                        <button
                          type="button"
                          onClick={() => handleQuickDresSubmit(true)}
                          className="text-[10px] bg-blue-600 hover:bg-blue-700 text-white font-bold px-2 py-0.5 rounded shadow-2xs cursor-pointer"
                        >
                          🚀 Nộp thật ngay
                        </button>
                      )}
                    </div>
                    <div className="text-[11px] font-normal leading-relaxed">{dresResult.message}</div>
                    {dresResult.rawDescription && (
                      <div className="text-[10px] text-gray-600 font-mono bg-white/70 p-1 rounded border border-gray-200">
                        {dresResult.rawDescription}
                      </div>
                    )}
                    {dresResult.message && dresResult.message.includes("yêu cầu định dạng TEXT") && (
                      <button
                        type="button"
                        onClick={() => {
                          setDresTaskType("QA");
                          setDresResult(null);
                        }}
                        className="mt-1 text-[11px] bg-blue-600 hover:bg-blue-700 text-white font-bold px-2 py-1 rounded shadow-2xs cursor-pointer self-start"
                      >
                        Chuyển sang tab Q&A ngay
                      </button>
                    )}
                  </div>
                )}

                </div>

                {/* Action Buttons */}
                <div className="flex flex-wrap justify-between items-center gap-2 px-4 py-3 border-t border-gray-200 bg-gray-50/90 shrink-0">
                  <button
                    type="button"
                    onClick={() => setShowDresModal(false)}
                    className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg font-semibold text-xs border border-gray-300 cursor-pointer"
                  >
                    Đóng
                  </button>

                  <div className="flex flex-wrap items-center gap-2">
                    {dresDryRun ? (
                      <>
                        <button
                          type="button"
                          disabled={dresIsSubmitting}
                          onClick={() => handleQuickDresSubmit(false)}
                          className="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white rounded-lg font-bold text-xs shadow-xs cursor-pointer"
                        >
                          {dresIsSubmitting ? "⏳ Đang thử..." : "🧪 Chạy Dry-Run"}
                        </button>
                        <button
                          type="button"
                          disabled={dresIsSubmitting}
                          onClick={() => handleQuickDresSubmit(true)}
                          className="px-4 py-1.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-lg font-bold text-xs shadow-md shadow-blue-500/20 cursor-pointer"
                        >
                          {dresIsSubmitting ? "⏳ Đang nộp..." : "🚀 Xác nhận Nộp Thật Ngay"}
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => {
                            setDresDryRun(true);
                            handleQuickDresSubmit(false, true);
                          }}
                          className="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white rounded-lg font-bold text-xs shadow-xs cursor-pointer"
                        >
                          🧪 Đổi sang Dry-Run
                        </button>
                        <button
                          type="button"
                          disabled={dresIsSubmitting}
                          onClick={() => handleQuickDresSubmit(false)}
                          className="px-4 py-1.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-lg font-bold text-xs shadow-md shadow-blue-500/20 cursor-pointer"
                        >
                          {dresIsSubmitting ? "⏳ Đang nộp..." : "🚀 Nộp ngay"}
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })()}
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
