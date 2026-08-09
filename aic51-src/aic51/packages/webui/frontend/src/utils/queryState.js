export const QUERY_HISTORY_KEY = "vecna-query-history";
export const TRIAGE_STATE_KEY = "vecna-query-triage";

export function normalizeTemporalQuery(query = "") {
  return String(query)
    .replace(/[|\\]/g, ";")
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean)
    .join(";");
}

export function getCandidateKey(frame = {}) {
  return frame.id || `${frame.video_id || ""}#${frame.frame_id || ""}`;
}

export function getFrameKeyframes(frame = {}) {
  const timeline = Array.isArray(frame.time_line) ? frame.time_line.filter(Boolean) : [];
  if (timeline.length > 0) return timeline.map(String);
  const fallback = frame.frame_id || String(frame.id || "").split("#")[1];
  return fallback ? [String(fallback)] : [];
}

export function getOcrBoxes(value) {
  const entries = Array.isArray(value)
    ? value
    : value?.bboxes || value?.boxes || value?.words || value?.data || [];
  if (!Array.isArray(entries)) return [];
  return entries.map((entry) => {
    const box = entry?.bbox || entry?.box || entry?.coordinates || entry;
    if (Array.isArray(box) && box.length >= 4) {
      return { text: entry?.text || entry?.word || "", x: box[0], y: box[1], width: box[2] - box[0], height: box[3] - box[1] };
    }
    if (box && typeof box === "object") {
      return {
        text: entry?.text || entry?.word || "",
        x: box.x ?? box.left ?? 0,
        y: box.y ?? box.top ?? 0,
        width: box.width ?? ((box.right ?? 0) - (box.x ?? box.left ?? 0)),
        height: box.height ?? ((box.bottom ?? 0) - (box.y ?? box.top ?? 0)),
      };
    }
    return null;
  }).filter((entry) => entry && entry.width > 0 && entry.height > 0);
}

export function groupTemporalCandidates(frames = []) {
  const candidates = new Map();

  frames.forEach((frame) => {
    const key = getCandidateKey(frame);
    const keyframes = getFrameKeyframes(frame);
    const scores = Array.isArray(frame.time_line_scores)
      ? frame.time_line_scores
      : keyframes.map(() => frame.scores);
    const existing = candidates.get(key);

    if (!existing) {
      candidates.set(key, {
        ...frame,
        id: key,
        keyframes,
        timelineScores: scores,
        primaryKeyframe: keyframes[0] || frame.frame_id,
      });
      return;
    }

    const mergedKeyframes = [...existing.keyframes];
    const mergedScores = [...existing.timelineScores];
    keyframes.forEach((keyframe, index) => {
      if (!mergedKeyframes.includes(keyframe)) {
        mergedKeyframes.push(keyframe);
        mergedScores.push(scores[index]);
      }
    });
    candidates.set(key, {
      ...existing,
      keyframes: mergedKeyframes,
      timelineScores: mergedScores,
    });
  });

  return [...candidates.values()];
}

export function getResultTotal(data = {}) {
  if (data.total !== undefined && data.total !== null) return Number(data.total) || 0;
  if (Array.isArray(data.frames)) return data.frames.length;
  if (Array.isArray(data.results)) return data.results.length;
  return 0;
}

export function serializeQueryState({
  query = "",
  params = {},
  offset = 0,
  selected,
  includeVideo = "",
  autoTranslate = false,
  id,
} = {}) {
  const next = { ...params, offset };
  if (id) next.id = id;
  else if (query) next.q = query;
  if (selected) next.selected = selected;
  if (includeVideo) next.include_video = includeVideo;
  if (autoTranslate) next.auto_translate = "true";
  return Object.fromEntries(
    Object.entries(next).filter(([, value]) => value !== undefined && value !== null && value !== ""),
  );
}

function resolveStorage(storage) {
  if (storage) return storage;
  if (typeof globalThis !== "undefined" && globalThis.localStorage) return globalThis.localStorage;
  return null;
}

export function loadQueryHistory(storage, key = QUERY_HISTORY_KEY) {
  const resolved = resolveStorage(storage);
  if (!resolved) return [];
  try {
    const value = JSON.parse(resolved.getItem(key) || "[]");
    return Array.isArray(value) ? value.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
}

export function rememberQuery(query, history = [], limit = 12) {
  const value = String(query || "").trim();
  if (!value) return history.slice(0, limit);
  return [value, ...history.filter((item) => item !== value)].slice(0, limit);
}

export function saveQueryHistory(history, storage, key = QUERY_HISTORY_KEY) {
  const resolved = resolveStorage(storage);
  if (resolved) resolved.setItem(key, JSON.stringify(history));
  return history;
}

export function clearQueryHistory(storage, key = QUERY_HISTORY_KEY) {
  const resolved = resolveStorage(storage);
  if (resolved) resolved.removeItem(key);
  return [];
}

export function triageKey(queryKey, frameId) {
  return `${queryKey || "all"}::${frameId}`;
}

export function updateTriageState(state = {}, queryKey, frameId, kind) {
  const key = triageKey(queryKey, frameId);
  const next = { ...state };
  const current = next[key] || {};
  if (kind === "shortlist") {
    next[key] = { ...current, shortlisted: !current.shortlisted, rejected: false };
  } else if (kind === "reject") {
    next[key] = { ...current, rejected: !current.rejected, shortlisted: false };
  }
  if (!next[key].shortlisted && !next[key].rejected) delete next[key];
  return next;
}

export function resetTriageState(state = {}, queryKey) {
  const prefix = `${queryKey || "all"}::`;
  return Object.fromEntries(Object.entries(state).filter(([key]) => !key.startsWith(prefix)));
}
