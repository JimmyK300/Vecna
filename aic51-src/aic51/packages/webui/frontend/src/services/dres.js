import axios from "axios";
import { getVideoMapKeyframes } from "./search.js";

export const DEFAULT_DRES_URL = "https://eventretrieval.one";
export const DRES_SERVER_KEY = "dres_server_url";
export const DRES_SESSION_KEY = "dres_session_id";
export const DRES_EVAL_KEY = "dres_eval_id";
export const DRES_HISTORY_KEY = "dres_submission_history";

/**
 * Clean video ID: removes video extensions (.mp4, .mkv, .webm, etc.)
 */
export function cleanVideoId(vid) {
  if (!vid) return "";
  const first = String(vid).split(",")[0].trim();
  return first.replace(/\.(mp4|webm|avi|mkv|mov|flv)$/i, "").trim();
}

/**
 * Format milliseconds into MM:SS.mmm format for display
 */
export function formatMsToTime(ms) {
  if (isNaN(ms) || ms < 0) return "00:00.000";
  const totalSec = ms / 1000;
  const minutes = Math.floor(totalSec / 60);
  const seconds = (totalSec % 60).toFixed(3);
  const minStr = String(minutes).padStart(2, "0");
  const secStr = seconds.padStart(6, "0");
  return `${minStr}:${secStr}`;
}

/**
 * Parse time string (seconds like "18.5" or MM:SS like "01:25" or "1:25.5") into seconds float
 */
export function parseTimeToSeconds(input) {
  if (!input) return 0;
  const str = String(input).trim();
  if (str.includes(":")) {
    const parts = str.split(":");
    if (parts.length === 2) {
      const min = parseFloat(parts[0]) || 0;
      const sec = parseFloat(parts[1]) || 0;
      return min * 60 + sec;
    } else if (parts.length === 3) {
      const hr = parseFloat(parts[0]) || 0;
      const min = parseFloat(parts[1]) || 0;
      const sec = parseFloat(parts[2]) || 0;
      return hr * 3600 + min * 60 + sec;
    }
  }
  const val = parseFloat(str);
  return isNaN(val) ? 0 : val;
}

/**
 * Intelligent time resolution using map-keyframes:
 * Reads workspace/map-keyframes/<video_id>.csv (n, pts_time, fps, frame_idx)
 * Maps frame index -> exact presentation timestamp in seconds & milliseconds.
 */
export async function resolveTimeFromFrame(videoId, frameId, currentTime = null, fallbackFps = 25) {
  const cleanVid = cleanVideoId(videoId);
  if (!cleanVid) {
    const tMs = currentTime ? Math.round(currentTime * 1000) : 0;
    return { time_ms: tMs, pts_time: tMs / 1000, fps: fallbackFps, source: "default" };
  }

  // 1. Fetch map-keyframes data
  let mapData = null;
  try {
    mapData = await getVideoMapKeyframes(cleanVid);
  } catch (err) {
    console.warn(`[DRES] map-keyframes lookup failed for ${cleanVid}:`, err);
  }

  const hasKeyframes = Boolean(
    mapData && mapData.available && Array.isArray(mapData.keyframes) && mapData.keyframes.length > 0
  );

  // 2. Discover true FPS:
  // Priority 1: map-keyframes
  // Priority 2: /api/file_info/${cleanVid}/0
  // Priority 3: fallbackFps
  let videoFps = fallbackFps;
  if (hasKeyframes) {
    const firstKf = mapData.keyframes[0];
    if (firstKf && firstKf.fps && !isNaN(Number(firstKf.fps)) && Number(firstKf.fps) > 0) {
      videoFps = Number(firstKf.fps);
    }
  } else {
    try {
      const infoRes = await axios.get(`/api/file_info/${cleanVid}/0`);
      if (infoRes.data && infoRes.data.fps && !isNaN(Number(infoRes.data.fps)) && Number(infoRes.data.fps) > 0) {
        videoFps = Number(infoRes.data.fps);
      }
    } catch (e) {}
  }

  const targetInt = parseInt(frameId, 10);

  // 3. If currentTime is provided from VideoPlayer and > 0, trust the player timestamp directly
  if (currentTime !== null && !isNaN(currentTime) && currentTime > 0) {
    const timeMs = Math.round(currentTime * 1000);
    return {
      time_ms: timeMs,
      pts_time: Number(currentTime),
      fps: videoFps,
      source: `player (${videoFps}fps)`,
    };
  }

  // 4. If map-keyframes data is available
  if (hasKeyframes && !isNaN(targetInt)) {
    const keyframes = mapData.keyframes;

    // A. Exact match on raw_idx or frame_idx
    let matched = keyframes.find((k) => k.raw_idx === targetInt || parseInt(k.frame_idx, 10) === targetInt);

    // B. Match on keyframe sequential number 'n' if within bounds
    if (!matched && targetInt <= keyframes.length && targetInt >= 1) {
      matched = keyframes.find((k) => k.n === targetInt);
    }

    if (matched && typeof matched.pts_time === "number") {
      const timeMs = Math.round(matched.pts_time * 1000);
      return {
        time_ms: timeMs,
        pts_time: matched.pts_time,
        fps: Number(matched.fps) || videoFps,
        raw_idx: matched.raw_idx,
        n: matched.n,
        source: `map-keyframes (${matched.pts_time.toFixed(3)}s, ${videoFps}fps)`,
      };
    }

    // C. Non-exact match: Frame is between keyframes -> Interpolate precisely using bounding keyframes!
    const sortedKf = [...keyframes].sort((a, b) => a.raw_idx - b.raw_idx);
    let prevKf = null;
    let nextKf = null;

    for (let i = 0; i < sortedKf.length; i++) {
      if (sortedKf[i].raw_idx <= targetInt) {
        prevKf = sortedKf[i];
      }
      if (sortedKf[i].raw_idx >= targetInt) {
        nextKf = sortedKf[i];
        break;
      }
    }

    if (prevKf && nextKf && prevKf.raw_idx !== nextKf.raw_idx) {
      // Linear interpolation between the two bounding keyframes
      const frameSpan = nextKf.raw_idx - prevKf.raw_idx;
      const timeSpan = nextKf.pts_time - prevKf.pts_time;
      const ratio = (targetInt - prevKf.raw_idx) / frameSpan;
      const interpolatedPts = prevKf.pts_time + ratio * timeSpan;
      const timeMs = Math.round(interpolatedPts * 1000);

      return {
        time_ms: timeMs,
        pts_time: interpolatedPts,
        fps: videoFps,
        source: `map-keyframes interpolated (${videoFps}fps)`,
      };
    } else if (prevKf) {
      // After last keyframe or after prevKf
      const diffFrames = targetInt - prevKf.raw_idx;
      const extrapolatedPts = prevKf.pts_time + diffFrames / videoFps;
      const timeMs = Math.round(extrapolatedPts * 1000);

      return {
        time_ms: timeMs,
        pts_time: extrapolatedPts,
        fps: videoFps,
        source: `map-keyframes (${videoFps}fps)`,
      };
    } else if (nextKf) {
      // Before first keyframe
      const diffFrames = nextKf.raw_idx - targetInt;
      const extrapolatedPts = Math.max(0, nextKf.pts_time - diffFrames / videoFps);
      const timeMs = Math.round(extrapolatedPts * 1000);

      return {
        time_ms: timeMs,
        pts_time: extrapolatedPts,
        fps: videoFps,
        source: `map-keyframes (${videoFps}fps)`,
      };
    }
  }

  // 5. Fallback calculation using true videoFps (never blindly 25fps)
  let timeSeconds = 0;
  if (!isNaN(targetInt)) {
    timeSeconds = targetInt / videoFps;
  }

  return {
    time_ms: Math.round(timeSeconds * 1000),
    pts_time: timeSeconds,
    fps: videoFps,
    source: `calc (${videoFps}fps)`,
  };
}

/**
 * Universal DRES Fetch with CORS proxy fallback
 */
export async function dresFetch(path, options = {}, customServerUrl = null) {
  const serverUrl = (customServerUrl || localStorage.getItem(DRES_SERVER_KEY) || DEFAULT_DRES_URL).trim().replace(/\/$/, "");
  const endpoint = path.startsWith("/") ? path : `/${path}`;

  // 1. Try via VECNA backend proxy to bypass CORS
  try {
    const proxyUrl = `/api/dres-proxy${endpoint}`;
    const proxyHeaders = {
      ...(options.headers || {}),
      "x-dres-server-url": serverUrl,
    };
    const resp = await fetch(proxyUrl, {
      ...options,
      headers: proxyHeaders,
    });
    if (resp.status !== 502) {
      return resp;
    }
  } catch (proxyErr) {
    // Backend proxy not reachable, continue to direct fetch
  }

  // 2. Fallback direct fetch
  const directUrl = `${serverUrl}${endpoint}`;
  return await fetch(directUrl, options);
}

/**
 * 1. Login to DRES
 */
export async function loginDres(username, password, serverUrl = null) {
  const resp = await dresFetch(
    "/api/v2/login",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    },
    serverUrl
  );

  let data = {};
  try {
    data = await resp.json();
  } catch (e) {
    data = { description: await resp.text() };
  }

  return { ok: resp.ok, status: resp.status, data };
}

/**
 * 2. Get User Info & check Session
 */
export async function getDresUser(sessionId, serverUrl = null) {
  if (!sessionId) return { ok: false, status: 400, data: { description: "Missing Session ID" } };
  const resp = await dresFetch(`/api/v2/user?session=${encodeURIComponent(sessionId)}`, {}, serverUrl);
  let data = {};
  try {
    data = await resp.json();
  } catch (e) {
    data = { description: await resp.text() };
  }
  return { ok: resp.ok, status: resp.status, data };
}

/**
 * 3. List Evaluations
 */
export async function getDresEvaluations(sessionId, serverUrl = null) {
  if (!sessionId) return { ok: false, status: 400, data: [] };
  const resp = await dresFetch(`/api/v2/client/evaluation/list?session=${encodeURIComponent(sessionId)}`, {}, serverUrl);
  let data = [];
  try {
    data = await resp.json();
  } catch (e) {
    data = [];
  }
  return { ok: resp.ok, status: resp.status, data: Array.isArray(data) ? data : [] };
}

/**
 * 4. Get Current Task
 */
export async function getDresCurrentTask(evaluationId, sessionId, serverUrl = null) {
  if (!evaluationId || !sessionId) return { ok: false, status: 400, data: null };
  const resp = await dresFetch(
    `/api/v2/client/evaluation/currentTask/${encodeURIComponent(evaluationId)}?session=${encodeURIComponent(sessionId)}`,
    {},
    serverUrl
  );
  let data = null;
  try {
    data = await resp.json();
  } catch (e) {
    data = null;
  }
  return { ok: resp.ok, status: resp.status, data };
}

/**
 * 4b. Get Evaluation State (includes timeLeft and taskStatus)
 */
export async function getDresEvaluationState(evaluationId, sessionId, serverUrl = null) {
  if (!evaluationId || !sessionId) return { ok: false, status: 400, data: null };
  const resp = await dresFetch(
    `/api/v2/evaluation/${encodeURIComponent(evaluationId)}/state?session=${encodeURIComponent(sessionId)}`,
    {},
    serverUrl
  );
  let data = null;
  try {
    data = await resp.json();
  } catch (e) {
    data = null;
  }
  return { ok: resp.ok, status: resp.status, data };
}

/**
 * 4c. Get Evaluation Info (includes taskTemplates list)
 */
export async function getDresEvaluationInfo(evaluationId, sessionId, serverUrl = null) {
  if (!evaluationId || !sessionId) return { ok: false, status: 400, data: null };
  const resp = await dresFetch(
    `/api/v2/evaluation/${encodeURIComponent(evaluationId)}/info?session=${encodeURIComponent(sessionId)}`,
    {},
    serverUrl
  );
  let data = null;
  try {
    data = await resp.json();
  } catch (e) {
    data = null;
  }
  return { ok: resp.ok, status: resp.status, data };
}

/**
 * 5. Submit Answer
 */
export async function submitDresAnswer(evaluationId, sessionId, payload, serverUrl = null) {
  if (!evaluationId || !sessionId) {
    return {
      ok: false,
      status: 400,
      data: { description: "Missing Evaluation ID or Session ID" },
    };
  }

  const resp = await dresFetch(
    `/api/v2/submit/${encodeURIComponent(evaluationId)}?session=${encodeURIComponent(sessionId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    serverUrl
  );

  let data = {};
  try {
    data = await resp.json();
  } catch (e) {
    data = { description: await resp.text() };
  }

  return { ok: resp.ok, status: resp.status, data };
}

/**
 * Parse DRES API error responses with clear, actionable Vietnamese messages
 */
export function parseDresError(res) {
  if (!res) return "Lỗi không xác định";
  const desc = res.data?.description || (typeof res.data === "string" ? res.data : "") || "";

  if (desc.includes("does not include textual information")) {
    return "Lỗi 412: Đề thi này trên DRES yêu cầu định dạng TEXT (như Q&A hoặc TRAKE). Vui lòng chuyển sang tab Q&A hoặc TRAKE để nộp đáp án!";
  }
  if (desc.includes("does include non-temporal information")) {
    return "Lỗi 412: Đề thi này trên DRES yêu cầu định dạng KIS (mediaItemName, start, end). Vui lòng chọn tab KIS!";
  }
  if (res.status === 412) {
    return desc || "Lỗi 412: Nộp trùng kết quả với lần nộp trước hoặc Task đã hết giờ!";
  }
  if (res.status === 401) {
    return "Lỗi 401: Token Session ID đã hết hạn, cần đăng nhập lại!";
  }
  if (res.status === 404) {
    return "Lỗi 404: Không tìm thấy Evaluation ID hoặc bài thi!";
  }
  return desc || `Mã lỗi HTTP: ${res.status}`;
}

/**
 * Helper to build DRES v2 Payload for all tasks
 */
export function buildPayload(type, { videoId, startMs = 0, endMs = null, answerText = "", framesList = [] }) {
  const vid = cleanVideoId(videoId);
  const sMs = Math.round(Number(startMs) || 0);
  const eMs = endMs !== null && !isNaN(Number(endMs)) ? Math.round(Number(endMs)) : sMs;

  if (type === "KIS" || type === "TKIS" || type === "VKIS") {
    return {
      type: "KIS",
      formattedText: `KIS: ${vid} @ ${sMs}ms`,
      payload: {
        answerSets: [
          {
            answers: [
              {
                mediaItemName: vid,
                start: sMs,
                end: eMs,
                text: `${vid} ${sMs}`,
              },
            ],
          },
        ],
      },
    };
  }

  if (type === "QA") {
    let cleanAns = String(answerText || "").trim();
    if (cleanAns.toUpperCase().startsWith("QA-")) cleanAns = cleanAns.substring(3).trim();
    const formatted = `QA-${cleanAns}-${vid}-${sMs}`;
    return {
      type: "QA",
      formattedText: formatted,
      payload: {
        answerSets: [
          {
            answers: [
              {
                text: formatted,
              },
            ],
          },
        ],
      },
    };
  }

  if (type === "TRAKE") {
    const frames = Array.isArray(framesList) ? framesList : String(framesList).split(/[,;\s]+/).map((f) => f.trim()).filter(Boolean);
    const formatted = `TR-${vid}-${frames.join(",")}`;
    return {
      type: "TRAKE",
      formattedText: formatted,
      payload: {
        answerSets: [
          {
            answers: [
              {
                text: formatted,
              },
            ],
          },
        ],
      },
    };
  }

  return {
    type: "UNKNOWN",
    formattedText: "",
    payload: {},
  };
}

/**
 * Submission history in localStorage
 */
export function getSubmissionHistory() {
  try {
    const raw = localStorage.getItem(DRES_HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    return [];
  }
}

export function saveSubmissionHistory(history) {
  try {
    localStorage.setItem(DRES_HISTORY_KEY, JSON.stringify(history));
  } catch (e) {}
}

export function addSubmissionHistoryEntry(entry) {
  const current = getSubmissionHistory();
  const updated = [
    {
      id: current.length + 1,
      timestamp: new Date().toLocaleTimeString(),
      ...entry,
    },
    ...current,
  ];
  saveSubmissionHistory(updated);
  return updated;
}

export function clearSubmissionHistory() {
  localStorage.removeItem(DRES_HISTORY_KEY);
  return [];
}
