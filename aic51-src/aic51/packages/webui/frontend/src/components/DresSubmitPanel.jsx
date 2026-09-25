import React, { useState, useEffect, useRef } from "react";
import {
  DEFAULT_DRES_URL,
  DRES_SERVER_KEY,
  DRES_SESSION_KEY,
  DRES_EVAL_KEY,
  cleanVideoId,
  formatMsToTime,
  parseTimeToSeconds,
  resolveTimeFromFrame,
  loginDres,
  getDresUser,
  getDresEvaluations,
  getDresCurrentTask,
  getDresEvaluationState,
  parseSecondsFromDres,
  formatDresTime,
  submitDresAnswer,
  buildPayload,
  parseDresError,
  getSubmissionHistory,
  addSubmissionHistoryEntry,
  clearSubmissionHistory,
} from "../services/dres.js";
import { useSelected } from "./SelectedProvider.jsx";

export default function DresSubmitPanel({ onLoadedAnswer, externalFillData = null }) {
  const { selected } = useSelected();

  // Accordion state (default expanded for quick access during competition)
  const [isExpanded, setIsExpanded] = useState(true);

  // Connection & Auth
  const [serverUrl, setServerUrl] = useState(() => localStorage.getItem(DRES_SERVER_KEY) || DEFAULT_DRES_URL);
  const [sessionId, setSessionId] = useState(() => localStorage.getItem(DRES_SESSION_KEY) || "");
  const [evaluations, setEvaluations] = useState([]);
  const [selectedEvalId, setSelectedEvalId] = useState(() => localStorage.getItem(DRES_EVAL_KEY) || "");
  const [userInfo, setUserInfo] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isCheckingConnection, setIsCheckingConnection] = useState(false);

  // Quick Login
  const [showLoginBox, setShowLoginBox] = useState(false);
  const [loginUsername, setLoginUsername] = useState("team_631");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginMsg, setLoginMsg] = useState("");

  // Live Task Monitor
  const [currentTask, setCurrentTask] = useState(null);
  const [taskRemainingSec, setTaskRemainingSec] = useState(null);
  const countdownIntervalRef = useRef(null);

  // Format Tabs: 'kis' | 'qa' | 'trake' | 'raw'
  const [currentTab, setCurrentTab] = useState("kis");

  // Form Fields
  const [videoInput, setVideoInput] = useState("");
  const [frameInput, setFrameInput] = useState("");
  const [timeMsInput, setTimeMsInput] = useState("");
  const [timeEndMsInput, setTimeEndMsInput] = useState("");
  const [timeCalcSource, setTimeCalcSource] = useState("");
  const [qaAnswerText, setQaAnswerText] = useState("");
  const [trakeFramesInput, setTrakeFramesInput] = useState("");
  const [rawJsonText, setRawJsonText] = useState("");

  // Options & Flags
  const [isDryRun, setIsDryRun] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Confirmation Modal
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [preparedPayload, setPreparedPayload] = useState(null);
  const [copiedJson, setCopiedJson] = useState(false);

  // Result Banner
  const [lastResult, setLastResult] = useState(null);

  // Audit History
  const [history, setHistory] = useState(() => getSubmissionHistory());
  const [showHistory, setShowHistory] = useState(false);

  // Save server & session changes to localStorage
  useEffect(() => {
    localStorage.setItem(DRES_SERVER_KEY, serverUrl);
  }, [serverUrl]);

  useEffect(() => {
    localStorage.setItem(DRES_SESSION_KEY, sessionId);
  }, [sessionId]);

  useEffect(() => {
    if (selectedEvalId && selectedEvalId.trim()) {
      localStorage.setItem(DRES_EVAL_KEY, selectedEvalId);
    }
  }, [selectedEvalId]);

  // Initial connection check on mount
  useEffect(() => {
    if (sessionId) {
      handleCheckConnection();
    }
  }, []);

  // Listen to externalFillData (e.g. from VideoPlayer or SavedAnswer)
  useEffect(() => {
    if (externalFillData) {
      applyFillData(externalFillData);
    }
  }, [externalFillData]);

  // Handle Countdown Timer for Current Task
  useEffect(() => {
    const isRunning = taskRemainingSec !== null && taskRemainingSec > 0;
    if (!isRunning) {
      if (countdownIntervalRef.current) {
        clearInterval(countdownIntervalRef.current);
        countdownIntervalRef.current = null;
      }
      return;
    }

    if (!countdownIntervalRef.current) {
      countdownIntervalRef.current = setInterval(() => {
        setTaskRemainingSec((prev) => {
          if (prev === null || prev <= 1) {
            clearInterval(countdownIntervalRef.current);
            countdownIntervalRef.current = null;
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }
  }, [taskRemainingSec > 0]);

  useEffect(() => {
    return () => {
      if (countdownIntervalRef.current) clearInterval(countdownIntervalRef.current);
    };
  }, []);

  // Check connection and fetch evaluations
  const handleCheckConnection = async () => {
    if (!sessionId.trim()) {
      setIsConnected(false);
      return;
    }
    setIsCheckingConnection(true);
    setLastResult(null);

    try {
      // 1. Check user info
      const uRes = await getDresUser(sessionId.trim(), serverUrl);
      if (uRes.ok && uRes.data) {
        setUserInfo(uRes.data);
        setIsConnected(true);
      } else {
        setIsConnected(false);
        setUserInfo(null);
      }

      // 2. Fetch evaluations
      const eRes = await getDresEvaluations(sessionId.trim(), serverUrl);
      if (eRes.ok && Array.isArray(eRes.data)) {
        setEvaluations(eRes.data);
        const currentSaved = (selectedEvalId || localStorage.getItem(DRES_EVAL_KEY) || "").trim();
        const matchedSaved = currentSaved ? eRes.data.find((e) => e.id === currentSaved) : null;
        const chosenEval = matchedSaved || eRes.data.find((e) => String(e.status).toUpperCase() === "ACTIVE") || eRes.data[0];
        if (chosenEval) {
          setSelectedEvalId(chosenEval.id);
          localStorage.setItem(DRES_EVAL_KEY, chosenEval.id);
          fetchCurrentTaskInfo(chosenEval.id);
        }
      }
    } catch (err) {
      setIsConnected(false);
    } finally {
      setIsCheckingConnection(false);
    }
  };

  // Perform quick login to obtain new session ID
  const handleLogin = async () => {
    if (!loginUsername || !loginPassword) {
      setLoginMsg("Vui lòng điền Username và Password!");
      return;
    }
    setLoginMsg("Đang đăng nhập...");
    try {
      const res = await loginDres(loginUsername, loginPassword, serverUrl);
      if (res.ok && res.data && res.data.sessionId) {
        setSessionId(res.data.sessionId);
        setLoginMsg("✅ Đăng nhập thành công!");
        setShowLoginBox(false);
        setTimeout(() => handleCheckConnection(), 300);
      } else {
        setLoginMsg(`❌ Thất bại: ${res.data.description || "Sai thông tin đăng nhập"}`);
      }
    } catch (err) {
      setLoginMsg(`❌ Lỗi kết nối: ${err.message}`);
    }
  };

  // Handle selection of evaluation ID (persist & dispatch event to VideoPlayer)
  const handleSelectEvalId = (newId) => {
    if (!newId) return;
    setSelectedEvalId(newId);
    localStorage.setItem(DRES_EVAL_KEY, newId);
    window.dispatchEvent(new CustomEvent("dres_eval_changed", { detail: { evalId: newId } }));
    fetchCurrentTaskInfo(newId);
  };

  // Periodic background sync with server for DresSubmitPanel (every 8s)
  useEffect(() => {
    if (!sessionId || !selectedEvalId) return;
    const interval = setInterval(() => {
      fetchCurrentTaskInfo(selectedEvalId);
    }, 8000);
    return () => clearInterval(interval);
  }, [sessionId, selectedEvalId]);

  // Sync when DRES_EVAL_KEY changes from VideoPlayer (in-tab custom event or cross-tab storage event)
  useEffect(() => {
    const handleStorageChange = (e) => {
      if (e.key === DRES_EVAL_KEY && e.newValue && e.newValue !== selectedEvalId) {
        setSelectedEvalId(e.newValue);
        fetchCurrentTaskInfo(e.newValue);
      }
    };
    const handleCustomChange = (e) => {
      const newId = e.detail?.evalId;
      if (newId && newId !== selectedEvalId) {
        setSelectedEvalId(newId);
        fetchCurrentTaskInfo(newId);
      }
    };
    window.addEventListener("storage", handleStorageChange);
    window.addEventListener("dres_eval_changed", handleCustomChange);
    return () => {
      window.removeEventListener("storage", handleStorageChange);
      window.removeEventListener("dres_eval_changed", handleCustomChange);
    };
  }, [selectedEvalId]);

  // Fetch Current Task details and auto-switch tab (NEVER blindly reset to 5 minutes!)
  const fetchCurrentTaskInfo = async (evalId = selectedEvalId) => {
    if (!evalId || !sessionId) return;
    try {
      const [taskRes, stateRes] = await Promise.all([
        getDresCurrentTask(evalId, sessionId, serverUrl).catch(() => ({ ok: false })),
        getDresEvaluationState(evalId, sessionId, serverUrl).catch(() => ({ ok: false })),
      ]);

      if (taskRes.ok && taskRes.data) {
        setCurrentTask(taskRes.data);
        // Auto-switch tab based on task group / task type
        const grp = String(taskRes.data.taskGroup || taskRes.data.taskType || taskRes.data.name || "").toUpperCase();
        if (grp.includes("QA")) {
          setCurrentTab("qa");
        } else if (grp.includes("TRAKE") || grp.includes("TR-")) {
          setCurrentTab("trake");
        } else {
          setCurrentTab("kis");
        }
      } else {
        setCurrentTask(null);
      }

      if (stateRes.ok && stateRes.data) {
        const state = stateRes.data;
        const rawLeft = state.timeLeft ?? state.task?.timeLeft ?? state.currentTask?.timeLeft ?? taskRes.data?.timeLeft;
        if (rawLeft !== undefined && rawLeft !== null) {
          const sec = parseSecondsFromDres(rawLeft);
          if (state.taskStatus === "RUNNING" || (taskRes.ok && state.taskStatus !== "ENDED")) {
            setTaskRemainingSec((prev) => {
              if (sec === null) return null;
              if (prev === null || Math.abs(prev - sec) > 2) {
                return Math.max(0, sec);
              }
              return prev;
            });
          } else if (state.taskStatus === "ENDED" || state.taskStatus === "IGNORED") {
            setTaskRemainingSec(0);
          } else {
            setTaskRemainingSec(null);
          }
        } else if (state.taskStatus === "ENDED") {
          setTaskRemainingSec(0);
        } else {
          setTaskRemainingSec(null);
        }
      } else if (taskRes.ok && taskRes.data?.timeLeft !== undefined && taskRes.data?.timeLeft !== null) {
        const sec = parseSecondsFromDres(taskRes.data.timeLeft);
        setTaskRemainingSec((prev) => {
          if (sec === null) return null;
          if (prev === null || Math.abs(prev - sec) > 2) {
            return Math.max(0, sec);
          }
          return prev;
        });
      } else if (!taskRes.ok) {
        setTaskRemainingSec(null);
      }
    } catch (err) {
      setCurrentTask(null);
      setTaskRemainingSec(null);
    }
  };

  // Auto-fill from external data or selected frame
  const applyFillData = async (data) => {
    if (!data) return;
    setIsExpanded(true);

    const vid = cleanVideoId(data.video_id || data.videoId);
    if (vid) setVideoInput(vid);

    const frame = data.frame_id || data.frame_counter || data.frameId || "";
    if (frame !== undefined && frame !== null) setFrameInput(String(frame));

    // Resolve exact time from map-keyframes
    if (vid && (frame || data.time !== undefined)) {
      const resolved = await resolveTimeFromFrame(vid, frame, data.time, data.fps || 25);
      setTimeMsInput(String(resolved.time_ms));
      setTimeEndMsInput(String(resolved.time_ms));
      setTimeCalcSource(resolved.source);
    }

    if (data.answer) setQaAnswerText(String(data.answer));
    if (data.frames) {
      if (Array.isArray(data.frames)) {
        setTrakeFramesInput(data.frames.join(", "));
      } else {
        setTrakeFramesInput(String(data.frames));
      }
    }

    if (data.type) {
      const t = String(data.type).toLowerCase();
      if (t.includes("qa")) setCurrentTab("qa");
      else if (t.includes("trake")) setCurrentTab("trake");
      else setCurrentTab("kis");
    }
  };

  // Auto-fill from current Selected Frames in VECNA
  const handleAutoFillFromSelected = async () => {
    if (!selected || selected.length === 0) {
      alert("Chưa có frame nào được chọn trong VECNA! Hãy click chọn 1 frame trên lưới kết quả.");
      return;
    }

    const firstItem = selected[0];
    let vId = "";
    let fId = "";

    if (typeof firstItem === "string" && firstItem.includes("#")) {
      const parts = firstItem.split("#");
      vId = parts[0];
      fId = parts[1];
    }

    if (!vId) {
      alert("Không nhận diện được Video ID của frame đã chọn!");
      return;
    }

    // Collect all frame IDs if user selected multiple frames (useful for TRAKE)
    const allFrames = selected
      .map((s) => (typeof s === "string" && s.includes("#") ? s.split("#")[1] : null))
      .filter(Boolean);

    await applyFillData({
      video_id: vId,
      frame_id: fId,
      frames: allFrames,
    });
  };

  // Build the current payload based on active tab
  const constructCurrentSubmission = () => {
    const cleanVid = cleanVideoId(videoInput);

    if (currentTab === "raw") {
      try {
        const parsed = JSON.parse(rawJsonText);
        return {
          type: "RAW_JSON",
          video: cleanVid || "CUSTOM",
          details: "Custom Raw JSON Payload",
          payload: parsed,
        };
      } catch (err) {
        return { error: `Cú pháp JSON không hợp lệ: ${err.message}` };
      }
    }

    if (currentTab === "kis") {
      const startMs = parseInt(timeMsInput, 10) || 0;
      const endMs = timeEndMsInput.trim() ? parseInt(timeEndMsInput, 10) || startMs : startMs;
      const built = buildPayload("KIS", {
        videoId: cleanVid,
        startMs: startMs,
        endMs: endMs,
      });
      return {
        type: "KIS",
        video: cleanVid,
        details: `Start: ${startMs}ms, End: ${endMs}ms`,
        payload: built.payload,
      };
    }

    if (currentTab === "qa") {
      const timeMs = parseInt(timeMsInput, 10) || 0;
      const built = buildPayload("QA", {
        videoId: cleanVid,
        startMs: timeMs,
        answerText: qaAnswerText,
      });
      return {
        type: "QA",
        video: cleanVid,
        details: built.formattedText,
        payload: built.payload,
      };
    }

    if (currentTab === "trake") {
      const frameList = trakeFramesInput.split(/[,;\s]+/).map((f) => f.trim()).filter(Boolean);
      const built = buildPayload("TRAKE", {
        videoId: cleanVid,
        framesList: frameList,
      });
      return {
        type: "TRAKE",
        video: cleanVid,
        details: built.formattedText,
        payload: built.payload,
      };
    }

    return { error: "Loại câu hỏi không hợp lệ!" };
  };

  // Open confirmation / Dry-Run preview modal
  const handleOpenSubmitConfirm = () => {
    const sub = constructCurrentSubmission();
    if (sub.error) {
      alert(sub.error);
      return;
    }
    if (!sub.video && currentTab !== "raw") {
      alert("Vui lòng điền Video ID trước khi nộp!");
      return;
    }
    if (!isDryRun && (!selectedEvalId || !sessionId)) {
      alert("Chưa kết nối Evaluation ID hoặc Session ID! Hãy kiểm tra ở mục Cấu hình trên cùng.");
      return;
    }

    setPreparedPayload(sub);
    setCopiedJson(false);
    setShowConfirmModal(true);
  };

  // Copy JSON to clipboard
  const handleCopyJson = () => {
    if (!preparedPayload) return;
    navigator.clipboard.writeText(JSON.stringify(preparedPayload.payload, null, 2));
    setCopiedJson(true);
    setTimeout(() => setCopiedJson(false), 2000);
  };

  // Execute Submission (supports forceRealSubmit override)
  const handleExecuteSubmit = async (forceRealSubmit = false) => {
    setShowConfirmModal(false);
    if (!preparedPayload) return;

    const runAsDryRun = isDryRun && !forceRealSubmit;

    setIsSubmitting(true);
    setLastResult({
      status: "loading",
      message: runAsDryRun ? "Đang kiểm tra Dry-Run..." : "Đang gửi đáp án lên máy chủ DRES...",
    });

    // Dry Run mode
    if (runAsDryRun) {
      setTimeout(() => {
        setIsSubmitting(false);
        setLastResult({
          status: "dry_run",
          title: "DRY-RUN THÀNH CÔNG (GIẢ LẬP)",
          message: "Định dạng JSON payload chuẩn 100% theo quy chuẩn BTC. Sẵn sàng nộp thật!",
          payload: preparedPayload.payload,
        });

        const updatedHistory = addSubmissionHistoryEntry({
          type: preparedPayload.type,
          video: preparedPayload.video,
          details: preparedPayload.details,
          verdict: "DRY-RUN",
          note: "Kiểm tra giả lập",
        });
        setHistory(updatedHistory);
      }, 300);
      return;
    }

    try {
      const res = await submitDresAnswer(selectedEvalId, sessionId, preparedPayload.payload, serverUrl);

      if (res.ok) {
        const isCorrect = res.data && res.data.submission === "CORRECT";
        const isWrong = res.data && res.data.submission === "WRONG";
        const isIndeterminate = res.data && (res.data.submission === "INDETERMINATE" || res.data.submission === "UNDECIDABLE");

        let statusType = "success";
        if (isWrong) statusType = "wrong";
        else if (isIndeterminate) statusType = "pending";

        setLastResult({
          status: statusType,
          title: `KẾT QUẢ DRES: ${res.data.submission || "THÀNH CÔNG"}`,
          message: res.data.description || (isCorrect ? "Đáp án chính xác! Điểm đã được ghi nhận." : "Đáp án sai! Bị trừ 10 điểm."),
          details: res.data,
        });

        const updatedHistory = addSubmissionHistoryEntry({
          type: preparedPayload.type,
          video: preparedPayload.video,
          details: preparedPayload.details,
          verdict: res.data.submission || "SUCCESS",
          note: res.data.description || "",
        });
        setHistory(updatedHistory);
      } else {
        const errMsg = parseDresError(res);

        setLastResult({
          status: "error",
          title: `LỖI TỪ SERVER (${res.status})`,
          message: errMsg,
          rawDescription: res.data?.description,
          details: res.data,
        });

        const updatedHistory = addSubmissionHistoryEntry({
          type: preparedPayload.type,
          video: preparedPayload.video,
          details: preparedPayload.details,
          verdict: `ERROR ${res.status}`,
          note: errMsg,
        });
        setHistory(updatedHistory);
      }
    } catch (err) {
      setLastResult({
        status: "error",
        title: "LỖI KẾT NỐI MẠNG",
        message: err.message,
      });

      const updatedHistory = addSubmissionHistoryEntry({
        type: preparedPayload.type,
        video: preparedPayload.video,
        details: preparedPayload.details,
        verdict: "FAILED",
        note: err.message,
      });
      setHistory(updatedHistory);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Reload history entry back into form
  const handleReloadHistory = (item) => {
    if (!item) return;
    setIsExpanded(true);
    setVideoInput(item.video || "");

    const t = String(item.type).toUpperCase();
    if (t === "QA") {
      setCurrentTab("qa");
      if (item.details && item.details.startsWith("QA-")) {
        const parts = item.details.split("-");
        if (parts.length >= 4) {
          setQaAnswerText(parts[1]);
          setTimeMsInput(parts[3]);
        }
      }
    } else if (t === "TRAKE") {
      setCurrentTab("trake");
      if (item.details && item.details.startsWith("TR-")) {
        const idx = item.details.lastIndexOf("-");
        if (idx !== -1) {
          setTrakeFramesInput(item.details.substring(idx + 1));
        }
      }
    } else {
      setCurrentTab("kis");
      const match = String(item.details).match(/Start:\s*(\d+)ms/);
      if (match) {
        setTimeMsInput(match[1]);
        setTimeEndMsInput(match[1]);
      }
    }
  };

  // Live preview text for the current tab
  const getLivePreviewText = () => {
    const sub = constructCurrentSubmission();
    if (sub.error) return sub.error;
    return JSON.stringify(sub.payload, null, 2);
  };

  return (
    <div className="w-full flex flex-col bg-white border border-gray-300 rounded-lg shadow-sm mb-2 overflow-hidden text-gray-800 text-xs">
      {/* 1. Header Bar with Accordion Toggle */}
      <div
        className="flex items-center justify-between px-3 py-2 bg-gradient-to-r from-sky-50 via-blue-50 to-indigo-50 cursor-pointer select-none border-b border-gray-200"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <span className="font-extrabold text-blue-700 tracking-wide flex items-center gap-1.5">
            🎯 DRES SUBMITTER
          </span>
          <span
            className={`w-2.5 h-2.5 rounded-full inline-block ${
              isConnected ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]" : "bg-amber-400"
            }`}
            title={isConnected ? "Đã kết nối máy chủ DRES" : "Chưa kết nối DRES"}
          />
          {userInfo && (
            <span className="text-[10px] bg-white border border-gray-300 text-gray-700 px-1.5 py-0.5 rounded font-mono shadow-2xs">
              {userInfo.username || "Team"}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {currentTask && (
            <span className="text-[10px] bg-blue-100 border border-blue-300 text-blue-800 font-bold px-1.5 py-0.5 rounded shadow-2xs animate-pulse">
              Task: {currentTask.name || "Active"} {taskRemainingSec !== null && `(${formatDresTime(taskRemainingSec)})`}
            </span>
          )}
          <span className="text-gray-500 hover:text-gray-800 font-bold text-sm">
            {isExpanded ? "▲" : "▼"}
          </span>
        </div>
      </div>

      {/* 2. Collapsible Body */}
      {isExpanded && (
        <div className="p-2.5 flex flex-col gap-2">
          {/* A. Server & Session Configuration Row */}
          <div className="bg-gray-50 border border-gray-200 p-2.5 rounded-lg flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-blue-700">1. Cấu hình DRES</span>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setShowLoginBox(!showLoginBox)}
                  className="text-[10px] text-amber-700 hover:text-amber-800 underline font-semibold cursor-pointer"
                >
                  {showLoginBox ? "Đóng đăng nhập" : "🔑 Đăng nhập cấp Session"}
                </button>
                <button
                  type="button"
                  onClick={handleCheckConnection}
                  disabled={isCheckingConnection}
                  className="text-[10px] bg-white hover:bg-gray-100 text-blue-700 px-2 py-0.5 rounded border border-gray-300 font-bold shadow-2xs cursor-pointer"
                >
                  {isCheckingConnection ? "Đang kiểm tra..." : "🔄 Làm mới"}
                </button>
              </div>
            </div>

            {/* Quick Login Form */}
            {showLoginBox && (
              <div className="bg-amber-50/70 border border-amber-300 p-2 rounded flex flex-col gap-1.5 my-1 shadow-2xs">
                <div className="grid grid-cols-2 gap-1.5">
                  <input
                    type="text"
                    placeholder="Username"
                    value={loginUsername}
                    onChange={(e) => setLoginUsername(e.target.value)}
                    className="bg-white border border-gray-300 rounded px-1.5 py-1 text-gray-800 text-[11px] focus:outline-none focus:border-blue-500"
                  />
                  <input
                    type="password"
                    placeholder="Password"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    className="bg-white border border-gray-300 rounded px-1.5 py-1 text-gray-800 text-[11px] focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div className="flex justify-between items-center">
                  <button
                    type="button"
                    onClick={handleLogin}
                    className="bg-amber-500 hover:bg-amber-600 text-white font-bold px-2 py-0.5 rounded text-[11px] shadow-2xs cursor-pointer"
                  >
                    Đăng nhập lấy Token
                  </button>
                  <span className="text-[10px] text-amber-800 font-medium">{loginMsg}</span>
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-1.5">
              <div>
                <label className="text-[10px] text-gray-600 font-semibold block mb-0.5">Session Token:</label>
                <input
                  type="text"
                  placeholder="Session ID..."
                  value={sessionId}
                  onChange={(e) => setSessionId(e.target.value)}
                  className="w-full bg-white border border-gray-300 rounded px-1.5 py-1 text-gray-800 text-[11px] font-mono focus:outline-none focus:border-blue-500 shadow-2xs"
                />
              </div>

              <div>
                <label className="text-[10px] text-gray-600 font-semibold block mb-0.5">Evaluation ID:</label>
                <select
                  value={selectedEvalId}
                  onChange={(e) => handleSelectEvalId(e.target.value)}
                  className="w-full bg-white border border-gray-300 rounded px-1.5 py-1 text-gray-800 text-[11px] font-semibold focus:outline-none focus:border-blue-500 shadow-2xs cursor-pointer"
                >
                  {evaluations.length > 0 ? (
                    evaluations.map((ev) => (
                      <option key={ev.id} value={ev.id}>
                        {ev.name || ev.id} [{ev.status}]
                      </option>
                    ))
                  ) : (
                    <option value={selectedEvalId}>{selectedEvalId || "(Chưa có evaluation)"}</option>
                  )}
                </select>
              </div>
            </div>
          </div>

          {/* B. Format Selector Tabs */}
          <div className="flex border-b border-gray-200 gap-1 pt-1">
            {[
              { id: "kis", label: "🎬 KIS (Video/Time)" },
              { id: "qa", label: "❓ Q&A" },
              { id: "trake", label: "⏱️ TRAKE" },
              { id: "raw", label: "⚙️ Raw JSON" },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setCurrentTab(tab.id)}
                className={`px-2 py-1 text-[11px] font-bold rounded-t transition-colors cursor-pointer ${
                  currentTab === tab.id
                    ? "bg-blue-600 text-white border-t-2 border-blue-700 shadow-xs"
                    : "text-gray-600 hover:text-gray-900 hover:bg-gray-100"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* C. Format Form Inputs */}
          <div className="flex flex-col gap-1.5 bg-gray-50/70 p-2.5 rounded-lg border border-gray-200">
            {/* Quick Auto-Fill Action */}
            <div className="flex justify-between items-center">
              <span className="text-[10px] text-gray-600 font-bold">2. Nhập thông tin bài nộp:</span>
              <button
                type="button"
                onClick={handleAutoFillFromSelected}
                className="text-[10px] bg-sky-50 hover:bg-sky-100 text-sky-800 border border-sky-300 font-bold px-2 py-0.5 rounded shadow-2xs cursor-pointer"
                title="Lấy video và frame từ mục Selected Frames của VECNA"
              >
                📥 Lấy từ Selected ({selected.length})
              </button>
            </div>

            {/* TAB: KIS */}
            {currentTab === "kis" && (
              <div className="flex flex-col gap-1.5">
                <div className="grid grid-cols-2 gap-1.5">
                  <div>
                    <label className="text-[10px] text-gray-600 font-semibold block mb-0.5">Video ID (bỏ đuôi):</label>
                    <input
                      type="text"
                      placeholder="Ví dụ: L21_V001"
                      value={videoInput}
                      onChange={async (e) => {
                        const val = e.target.value;
                        setVideoInput(val);
                        if (val && frameInput) {
                          const res = await resolveTimeFromFrame(val, frameInput);
                          setTimeMsInput(String(res.time_ms));
                          setTimeEndMsInput(String(res.time_ms));
                          setTimeCalcSource(res.source);
                        }
                      }}
                      className="w-full bg-white border border-gray-300 rounded px-1.5 py-1 text-gray-800 text-xs font-mono font-semibold focus:outline-none focus:border-blue-500 shadow-2xs"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-gray-600 font-semibold block mb-0.5">
                      Số Frame (hoặc quy đổi):
                    </label>
                    <input
                      type="text"
                      placeholder="Ví dụ: 462"
                      value={frameInput}
                      onChange={async (e) => {
                        const val = e.target.value;
                        setFrameInput(val);
                        if (videoInput && val) {
                          const res = await resolveTimeFromFrame(videoInput, val);
                          setTimeMsInput(String(res.time_ms));
                          setTimeEndMsInput(String(res.time_ms));
                          setTimeCalcSource(res.source);
                        }
                      }}
                      className="w-full bg-white border border-gray-300 rounded px-1.5 py-1 text-gray-800 text-xs font-mono font-semibold focus:outline-none focus:border-blue-500 shadow-2xs"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-1.5">
                  <div>
                    <div className="flex justify-between items-center mb-0.5">
                      <label className="text-[10px] text-gray-600 font-semibold">Start (ms):</label>
                      {timeCalcSource && (
                        <span className="text-[9px] text-emerald-700 font-mono font-medium">
                          ✓ {timeCalcSource}
                        </span>
                      )}
                    </div>
                    <input
                      type="number"
                      placeholder="Mili-giây (ms)"
                      value={timeMsInput}
                      onChange={(e) => {
                        setTimeMsInput(e.target.value);
                        if (!timeEndMsInput) setTimeEndMsInput(e.target.value);
                      }}
                      className="w-full bg-white border border-gray-300 rounded px-1.5 py-1 text-gray-800 text-xs font-mono font-bold focus:outline-none focus:border-blue-500 shadow-2xs"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-gray-600 font-semibold block mb-0.5">End (ms - tuỳ chọn):</label>
                    <input
                      type="number"
                      placeholder="Mặc định = Start"
                      value={timeEndMsInput}
                      onChange={(e) => setTimeEndMsInput(e.target.value)}
                      className="w-full bg-white border border-gray-300 rounded px-1.5 py-1 text-gray-800 text-xs font-mono focus:outline-none focus:border-blue-500 shadow-2xs"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* TAB: QA */}
            {currentTab === "qa" && (
              <div className="flex flex-col gap-1.5">
                <div>
                  <label className="text-[10px] text-gray-600 font-semibold block mb-0.5">Câu trả lời (Answer Text):</label>
                  <input
                    type="text"
                    placeholder="Ví dụ: red car, blue bus, 42..."
                    value={qaAnswerText}
                    onChange={(e) => setQaAnswerText(e.target.value)}
                    className="w-full bg-white border border-gray-300 rounded px-1.5 py-1 text-gray-800 text-xs font-semibold focus:outline-none focus:border-blue-500 shadow-2xs"
                  />
                </div>

                <div className="grid grid-cols-2 gap-1.5">
                  <div>
                    <label className="text-[10px] text-gray-600 font-semibold block mb-0.5">Video ID:</label>
                    <input
                      type="text"
                      placeholder="Ví dụ: L21_V001"
                      value={videoInput}
                      onChange={(e) => setVideoInput(e.target.value)}
                      className="w-full bg-white border border-gray-300 rounded px-1.5 py-1 text-gray-800 text-xs font-mono font-semibold focus:outline-none focus:border-blue-500 shadow-2xs"
                    />
                  </div>
                  <div>
                    <div className="flex justify-between items-center mb-0.5">
                      <label className="text-[10px] text-gray-600 font-semibold">Thời gian (ms):</label>
                      {timeCalcSource && (
                        <span className="text-[9px] text-emerald-700 font-mono font-medium">
                          ✓ {timeCalcSource}
                        </span>
                      )}
                    </div>
                    <input
                      type="number"
                      placeholder="Mili-giây (ms)"
                      value={timeMsInput}
                      onChange={(e) => setTimeMsInput(e.target.value)}
                      className="w-full bg-white border border-gray-300 rounded px-1.5 py-1 text-gray-800 text-xs font-mono font-bold focus:outline-none focus:border-blue-500 shadow-2xs"
                    />
                  </div>
                </div>

                <div className="bg-white border border-gray-300 p-1.5 rounded font-mono text-[10px] text-emerald-700 truncate shadow-2xs">
                  Chuỗi: QA-{qaAnswerText || "<ANS>"}-{cleanVideoId(videoInput) || "<VID>"}-{timeMsInput || "0"}
                </div>
              </div>
            )}

            {/* TAB: TRAKE */}
            {currentTab === "trake" && (
              <div className="flex flex-col gap-1.5">
                <div>
                  <label className="text-[10px] text-gray-600 font-semibold block mb-0.5">Video ID duy nhất:</label>
                  <input
                    type="text"
                    placeholder="Ví dụ: L21_V001"
                    value={videoInput}
                    onChange={(e) => setVideoInput(e.target.value)}
                    className="w-full bg-white border border-gray-300 rounded px-1.5 py-1 text-gray-800 text-xs font-mono font-semibold focus:outline-none focus:border-blue-500 shadow-2xs"
                  />
                </div>
                <div>
                  <div className="flex justify-between items-center mb-0.5">
                    <label className="text-[10px] text-gray-600 font-semibold">
                      Danh sách Frame IDs (theo thứ tự sự kiện, cách nhau dấu phẩy):
                    </label>
                    {videoInput && (() => {
                      const cleanVid = cleanVideoId(videoInput);
                      const matchedBookmarked = (selected || [])
                        .filter((id) => id && cleanVideoId(id.split("#")[0]) === cleanVid)
                        .map((id) => parseInt(id.split("#")[1], 10))
                        .filter((n) => !isNaN(n))
                        .sort((a, b) => a - b);
                      if (matchedBookmarked.length === 0) return null;
                      return (
                        <button
                          type="button"
                          onClick={() => setTrakeFramesInput(matchedBookmarked.join(", "))}
                          className="text-[9px] bg-blue-50 hover:bg-blue-100 text-blue-700 font-semibold px-1.5 py-0.2 rounded border border-blue-200 cursor-pointer shadow-2xs"
                          title="Lấy các frame đã lưu của video này"
                        >
                          📋 Lấy {matchedBookmarked.length} frame đã lưu
                        </button>
                      );
                    })()}
                  </div>
                  <input
                    type="text"
                    placeholder="Ví dụ: 140, 395, 820, 1450"
                    value={trakeFramesInput}
                    onChange={(e) => setTrakeFramesInput(e.target.value)}
                    className="w-full bg-white border border-gray-300 rounded px-1.5 py-1 text-gray-800 text-xs font-mono font-semibold focus:outline-none focus:border-blue-500 shadow-2xs"
                  />
                </div>
                <div className="bg-white border border-gray-300 p-1.5 rounded font-mono text-[10px] text-emerald-700 truncate shadow-2xs">
                  Chuỗi: TR-{cleanVideoId(videoInput) || "<VID>"}-{trakeFramesInput ? trakeFramesInput.split(/[,;\s]+/).map((f) => f.trim()).filter(Boolean).join(",") : "<FRAMES>"}
                </div>
              </div>
            )}

            {/* TAB: RAW JSON */}
            {currentTab === "raw" && (
              <div className="flex flex-col gap-1.5">
                <textarea
                  rows={4}
                  placeholder='{"answerSets": [{"answers": [{"mediaItemName": "...", "start": 0, "end": 0}]}]}'
                  value={rawJsonText}
                  onChange={(e) => setRawJsonText(e.target.value)}
                  className="w-full bg-white border border-gray-300 rounded p-1.5 text-gray-800 font-mono text-[11px] focus:outline-none focus:border-blue-500 shadow-2xs"
                />
                <button
                  type="button"
                  onClick={() => {
                    try {
                      setRawJsonText(JSON.stringify(JSON.parse(rawJsonText), null, 2));
                    } catch (e) {
                      alert("JSON không hợp lệ!");
                    }
                  }}
                  className="text-[10px] bg-white hover:bg-gray-100 text-gray-700 self-end px-2 py-0.5 rounded border border-gray-300 shadow-2xs cursor-pointer"
                >
                  Format JSON
                </button>
              </div>
            )}

            {/* Live Payload Preview */}
            <div className="mt-0.5 bg-white border border-gray-300 p-1.5 rounded font-mono text-[10px] text-gray-800 max-h-24 overflow-y-auto shadow-2xs">
              <pre>{getLivePreviewText()}</pre>
            </div>
          </div>

          {/* D. Action & Submit Row */}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-1.5 cursor-pointer text-[11px] text-amber-800 font-semibold select-none">
                <input
                  type="checkbox"
                  checked={isDryRun}
                  onChange={(e) => setIsDryRun(e.target.checked)}
                  className="rounded text-amber-600 focus:ring-0 cursor-pointer"
                />
                <span>Chạy thử giả lập (Dry-Run)</span>
              </label>

              <button
                type="button"
                onClick={() => setShowHistory(!showHistory)}
                className="text-[10px] text-gray-600 hover:text-blue-600 underline cursor-pointer"
              >
                {showHistory ? "Ẩn lịch sử" : `Xem lịch sử (${history.length})`}
              </button>
            </div>

            <button
              type="button"
              disabled={isSubmitting}
              onClick={handleOpenSubmitConfirm}
              className={`w-full py-2 px-3 rounded-lg font-bold text-xs tracking-wider shadow-sm transition-all cursor-pointer ${
                isDryRun
                  ? "bg-amber-500 hover:bg-amber-600 text-white"
                  : "bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white shadow-blue-500/20"
              }`}
            >
              {isSubmitting
                ? "⏳ ĐANG NỘP LÊN DRES..."
                : isDryRun
                ? "🧪 KIỂM TRA DRY-RUN (XEM JSON)"
                : "🚀 BẤM NỘP BÀI (SUBMIT)"}
            </button>
          </div>

          {/* E. Result Display Banner */}
          {lastResult && (
            <div
              className={`p-2.5 rounded-lg border text-xs flex flex-col gap-1 animate-fadeIn shadow-2xs ${
                lastResult.status === "success"
                  ? "bg-emerald-50 border-emerald-300 text-emerald-900"
                  : lastResult.status === "wrong"
                  ? "bg-rose-50 border-rose-300 text-rose-900"
                  : lastResult.status === "pending"
                  ? "bg-amber-50 border-amber-300 text-amber-900"
                  : lastResult.status === "dry_run"
                  ? "bg-sky-50 border-sky-300 text-sky-900"
                  : "bg-rose-50 border-rose-400 text-rose-900"
              }`}
            >
              <div className="font-bold flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  {lastResult.status === "success" && "🟢"}
                  {lastResult.status === "wrong" && "🔴"}
                  {lastResult.status === "pending" && "🟡"}
                  {lastResult.status === "dry_run" && "🧪"}
                  {lastResult.status === "error" && "⚠️"}
                  <span>{lastResult.title}</span>
                </span>
                {lastResult.status === "dry_run" && (
                  <button
                    type="button"
                    onClick={() => handleExecuteSubmit(true)}
                    className="text-[10px] bg-blue-600 hover:bg-blue-700 text-white font-bold px-2 py-0.5 rounded shadow-2xs cursor-pointer"
                  >
                    🚀 Nộp thật ngay
                  </button>
                )}
              </div>
              <p className="text-[11px] leading-relaxed">{lastResult.message}</p>
              {lastResult.rawDescription && (
                <div className="text-[10px] text-gray-600 font-mono bg-white/70 p-1 rounded border border-gray-200">
                  {lastResult.rawDescription}
                </div>
              )}
            </div>
          )}

          {/* F. Audit History Table */}
          {showHistory && (
            <div className="bg-gray-50 p-2 rounded-lg border border-gray-200 flex flex-col gap-1 max-h-48 overflow-y-auto">
              <div className="flex justify-between items-center text-[10px] font-bold text-gray-600 border-b border-gray-200 pb-1">
                <span>Lịch sử nộp ({history.length}):</span>
                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm("Xóa toàn bộ lịch sử nộp DRES?")) {
                      clearSubmissionHistory();
                      setHistory([]);
                    }
                  }}
                  className="text-rose-600 hover:text-rose-700 text-[9px] cursor-pointer"
                >
                  Xóa
                </button>
              </div>

              {history.length === 0 ? (
                <div className="text-[10px] text-gray-500 italic py-2 text-center">Chưa có bài nộp nào.</div>
              ) : (
                history.map((it) => (
                  <div
                    key={it.id}
                    className="flex justify-between items-center py-1 border-b border-gray-200/80 text-[10px]"
                  >
                    <div className="flex flex-col min-w-0 pr-1">
                      <div className="flex items-center gap-1 font-mono">
                        <span className="text-gray-400">#{it.id}</span>
                        <span className="text-blue-700 font-bold">{it.type}</span>
                        <span className="text-gray-800 truncate font-semibold">{it.video}</span>
                      </div>
                      <span className="text-gray-500 text-[9px] truncate">{it.details}</span>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      <span
                        className={`px-1 py-0.5 rounded font-bold text-[9px] border ${
                          it.verdict === "CORRECT" || it.verdict === "SUCCESS"
                            ? "bg-emerald-50 text-emerald-800 border-emerald-300"
                            : it.verdict === "WRONG"
                            ? "bg-rose-50 text-rose-800 border-rose-300"
                            : it.verdict === "DRY-RUN"
                            ? "bg-sky-50 text-sky-800 border-sky-300"
                            : "bg-gray-100 text-gray-700 border-gray-300"
                        }`}
                      >
                        {it.verdict}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleReloadHistory(it)}
                        className="bg-white hover:bg-gray-100 text-blue-700 px-1.5 py-0.5 rounded text-[9px] font-bold border border-gray-300 shadow-2xs cursor-pointer"
                        title="Nạp lại vào form để sửa và gửi"
                      >
                        Nạp
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}

      {/* 3. Modal Xác nhận & Xem JSON Dry-Run (Màu trắng đồng bộ) */}
      {showConfirmModal && preparedPayload && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-2xs flex items-center justify-center p-3 animate-fadeIn">
          <div className="bg-white border border-gray-300 rounded-xl max-w-lg w-full p-4 shadow-2xl flex flex-col gap-3 text-gray-800 text-xs">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-gray-200 pb-2">
              <div className="flex items-center gap-2">
                <span className="text-base">{isDryRun ? "🧪" : "⚠️"}</span>
                <span className={`font-bold text-sm ${isDryRun ? "text-amber-700" : "text-rose-700"}`}>
                  {isDryRun ? "XEM JSON PAYLOAD (DRY-RUN)" : "XÁC NHẬN NỘP BÀI DRES THẬT"}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setShowConfirmModal(false)}
                className="text-gray-400 hover:text-gray-700 font-bold text-sm px-1.5 cursor-pointer"
              >
                ✕
              </button>
            </div>

            {/* Warning or Info Banner */}
            {isDryRun ? (
              <div className="bg-amber-50 border border-amber-300 p-2.5 rounded-lg text-amber-900 text-[11px] leading-relaxed">
                <strong>CHẾ ĐỘ DRY-RUN:</strong> Cấu trúc JSON bên dưới đã được chuẩn hoá theo DRES v2. Bạn có thể kiểm tra kỹ nội dung trước khi quyết định nộp thật!
              </div>
            ) : (
              <div className="bg-rose-50 border border-rose-300 p-2.5 rounded-lg text-rose-900 text-[11px] leading-relaxed">
                <strong>CẢNH BÁO PHẠT ĐIỂM:</strong> Nộp sai trước lần đúng đầu tiên sẽ bị <strong>trừ 10 điểm</strong>! Không nộp trùng kết quả cho cùng một task.
              </div>
            )}

            {/* Target Details Badge */}
            <div className="bg-gray-50 border border-gray-200 p-2 rounded-lg grid grid-cols-2 gap-2 text-[11px] font-mono">
              <div>
                <span className="text-gray-500">Evaluation: </span>
                <strong className="text-blue-700">{selectedEvalId || "N/A"}</strong>
              </div>
              <div>
                <span className="text-gray-500">Video ID: </span>
                <strong className="text-purple-700">{preparedPayload.video}</strong>
              </div>
              <div>
                <span className="text-gray-500">Loại Task: </span>
                <strong className="text-emerald-700">{preparedPayload.type}</strong>
              </div>
              <div>
                <span className="text-gray-500">Chi tiết: </span>
                <strong className="text-gray-800 truncate">{preparedPayload.details}</strong>
              </div>
            </div>

            {/* JSON Payload Display */}
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between text-[11px] font-semibold text-gray-600">
                <span>Cấu trúc JSON gửi lên máy chủ DRES:</span>
                <button
                  type="button"
                  onClick={handleCopyJson}
                  className="text-blue-600 hover:text-blue-800 text-[10px] font-bold flex items-center gap-1 cursor-pointer"
                >
                  {copiedJson ? "✓ Đã chép!" : "📋 Sao chép JSON"}
                </button>
              </div>
              <div className="bg-gray-50 border border-gray-300 p-2.5 rounded-lg max-h-56 overflow-y-auto text-xs font-mono text-gray-900 shadow-inner">
                <pre>{JSON.stringify(preparedPayload.payload, null, 2)}</pre>
              </div>
            </div>

            {/* Modal Actions */}
            <div className="flex justify-between items-center pt-2 border-t border-gray-200">
              <button
                type="button"
                onClick={() => setShowConfirmModal(false)}
                className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg font-semibold text-xs border border-gray-300 cursor-pointer"
              >
                ✕ Đóng / Sửa lại
              </button>

              <div className="flex items-center gap-2">
                {isDryRun ? (
                  <>
                    <button
                      type="button"
                      onClick={() => handleExecuteSubmit(false)}
                      className="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white rounded-lg font-bold text-xs shadow-xs cursor-pointer"
                    >
                      🧪 Chỉ chạy Dry-Run
                    </button>
                    <button
                      type="button"
                      onClick={() => handleExecuteSubmit(true)}
                      className="px-4 py-1.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-lg font-bold text-xs shadow-md shadow-blue-500/20 cursor-pointer"
                    >
                      🚀 Xác nhận Nộp Thật Ngay
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        setIsDryRun(true);
                        handleExecuteSubmit(false);
                      }}
                      className="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white rounded-lg font-bold text-xs shadow-xs cursor-pointer"
                    >
                      🧪 Đổi sang Dry-Run
                    </button>
                    <button
                      type="button"
                      onClick={() => handleExecuteSubmit(true)}
                      className="px-4 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg font-bold text-xs shadow-md shadow-rose-500/20 cursor-pointer"
                    >
                      🚀 Đồng ý Nộp Thật Ngay
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
