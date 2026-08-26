import localforage from "localforage";
import JSZip from "jszip";

// Automatically clear/reset all saved answers in localforage when app opens/reloads
localforage.setItem("answers", []);
localforage.setItem("id_ptr", 0);

export function formatCleanInteger(val) {
  if (val === null || val === undefined) return "0";
  const num = typeof val === "number" ? val : parseFloat(String(val).replace(/e.*/i, ""));
  if (isNaN(num)) return String(val).trim();
  return String(Math.round(num));
}

export function extractAnswerFrameItems(answer) {
  let items = [];

  if (answer.raw_selected) {
    let rawList = [];
    if (Array.isArray(answer.raw_selected)) {
      rawList = answer.raw_selected;
    } else if (typeof answer.raw_selected === "string" && answer.raw_selected.trim()) {
      rawList = answer.raw_selected.split(";").map((s) => s.trim()).filter(Boolean);
    }

    rawList.forEach((str) => {
      const parts = str.split("#");
      if (parts.length >= 2) {
        const vId = parts[0].trim();
        const rawFramePart = parts[1].trim();
        if (vId && vId !== "undefined" && vId !== "null") {
          const subFrames = rawFramePart.split(",").map((s) => parseInt(formatCleanInteger(s), 10)).filter((n) => !isNaN(n));
          subFrames.forEach((fId) => {
            items.push({ video_id: vId, frame_counter: fId });
          });
        }
      }
    });
  }

  if (items.length === 0) {
    let videoIds = [];
    if (typeof answer.video_id === "string" && answer.video_id.includes(",")) {
      videoIds = answer.video_id
        .split(",")
        .map((v) => v.trim())
        .filter((v) => v && v !== "undefined" && v !== "null");
    } else if (answer.video_id && String(answer.video_id).trim() !== "undefined" && String(answer.video_id).trim() !== "null") {
      videoIds = [String(answer.video_id).trim()];
    }

    let frameCounters = [];
    if (Array.isArray(answer.frame_counter)) {
      frameCounters = answer.frame_counter.map((fc) => parseInt(formatCleanInteger(fc), 10));
    } else if (typeof answer.frame_counter === "string" && answer.frame_counter.includes(",")) {
      frameCounters = answer.frame_counter.split(",").map((fc) => parseInt(formatCleanInteger(fc), 10));
    } else if (answer.frame_counter !== undefined && answer.frame_counter !== null) {
      frameCounters = [parseInt(formatCleanInteger(answer.frame_counter), 10)];
    } else if (answer.frame_id) {
      frameCounters = [parseInt(formatCleanInteger(answer.frame_id), 10)];
    }

    if (videoIds.length > 0 && frameCounters.length > 0) {
      for (let i = 0; i < frameCounters.length; i++) {
        const vId = videoIds[i] || videoIds[0];
        if (vId && vId !== "undefined" && vId !== "null") {
          items.push({ video_id: vId, frame_counter: frameCounters[i] });
        }
      }
    }
  }

  return items;
}

export function extractQAAnswers(answer) {
  let list = [];
  if (answer.qa_answers) {
    if (Array.isArray(answer.qa_answers)) {
      list = answer.qa_answers.map((a) => String(a).trim()).filter(Boolean);
    } else if (typeof answer.qa_answers === "string" && answer.qa_answers.trim()) {
      list = answer.qa_answers.split("|").map((a) => a.trim()).filter(Boolean);
    }
  }

  if (list.length === 0 && answer.answer) {
    if (typeof answer.answer === "string" && answer.answer.trim()) {
      list = answer.answer.split("|").map((a) => a.trim()).filter(Boolean);
    } else if (Array.isArray(answer.answer)) {
      list = answer.answer.map((a) => String(a).trim()).filter(Boolean);
    }
  }

  return list;
}

export function processAnswer(answer) {
  if ("time" in answer) answer.time = parseFloat(answer.time);
  if (answer.raw_selected && typeof answer.raw_selected === "string" && answer.raw_selected.trim()) {
    answer.raw_selected = answer.raw_selected.split(";").map((s) => s.trim()).filter(Boolean);
  }
  if (answer.qa_answers && typeof answer.qa_answers === "string" && answer.qa_answers.trim()) {
    answer.qa_answers = answer.qa_answers.split("|").map((a) => a.trim()).filter(Boolean);
  }
  if ("frame_counter" in answer) {
    if (typeof answer.frame_counter === 'string' && answer.frame_counter.includes(',')) {
      answer.frame_counter = answer.frame_counter.split(',').map(fc => fc.trim());
    } else if (!Array.isArray(answer.frame_counter)) {
      answer.frame_counter = [answer.frame_counter];
    }
  }
  if ("correct" in answer) answer.correct = parseInt(answer.correct);

  const items = extractAnswerFrameItems(answer);
  if (items.length > 0) {
    answer.video_id = items.map((it) => it.video_id).join(",");
    answer.frame_counter = items.map((it) => String(it.frame_counter));
    answer.frame_id = String(items[0].frame_counter);
  }
  return answer;
}

export async function getAnswers() {
  const answers = await localforage.getItem("answers");
  let res = null;
  if (!answers) {
    res = [];
  } else {
    res = answers;
  }
  return res;
}
export async function getAnswersByIds(ids) {
  const answers = await localforage.getItem("answers");
  if (!answers) {
    return [];
  }
  return answers.filter((answer) => ids.includes(answer.id));
}

export async function addAnswer(answer) {
  const answers = await getAnswers();
  processAnswer(answer);
  let id = parseInt((await localforage.getItem("id_ptr")) || 0);
  await localforage.setItem("answers", [
    ...answers,
    { id: id, submitted: new Date().toLocaleString(), ...answer },
  ]);
  const res = await localforage.getItem("answers");
  await localforage.setItem("id_ptr", id + 1);
  return res;
}

export async function updateAnswer(id, new_answer) {
  const answers = await getAnswers();
  processAnswer(new_answer);
  const updatedAnswer = answers.map((answer) => {
    if (answer.id === parseInt(id)) {
      return {
        id: parseInt(id),
        submitted: answer.submitted,
        frame_id: answer.frame_id,
        ...new_answer,
      };
    } else {
      return answer;
    }
  });
  await localforage.setItem("answers", updatedAnswer);
  return await localforage.getItem("answers");
}

export async function deleteAnswer(id) {
  const answers = await getAnswers();
  const newAnswers = answers.filter(
    (answer) => parseInt(answer.id) !== parseInt(id),
  );
  await localforage.setItem("answers", newAnswers);
  return await localforage.getItem("answers");
}

export async function clearAllAnswers() {
  await localforage.setItem("answers", []);
  await localforage.setItem("id_ptr", 0);
  return [];
}

import { getVideoMaxFrame } from "./search.js";

export function extractAnswerSequences(answer) {
  let sequences = [];

  if (answer.raw_selected) {
    let rawList = [];
    if (Array.isArray(answer.raw_selected)) {
      rawList = answer.raw_selected;
    } else if (typeof answer.raw_selected === "string" && answer.raw_selected.trim()) {
      rawList = answer.raw_selected.split(";").map((s) => s.trim()).filter(Boolean);
    }

    rawList.forEach((str) => {
      const parts = str.split("#");
      if (parts.length >= 2) {
        const vId = parts[0].trim();
        const rawFramePart = parts[1].trim();
        if (vId && vId !== "undefined" && vId !== "null") {
          const subFrames = rawFramePart
            .split(",")
            .map((s) => parseInt(formatCleanInteger(s), 10))
            .filter((n) => !isNaN(n));
          if (subFrames.length > 0) {
            sequences.push({ video_id: vId, frames: subFrames });
          }
        }
      }
    });
  }

  if (sequences.length === 0) {
    const items = extractAnswerFrameItems(answer);
    if (items.length > 0) {
      const map = new Map();
      items.forEach((item) => {
        if (!map.has(item.video_id)) {
          map.set(item.video_id, []);
        }
        map.get(item.video_id).push(item.frame_counter);
      });
      sequences = Array.from(map.entries()).map(([vId, frames]) => ({
        video_id: vId,
        frames: frames,
      }));
    }
  }

  return sequences;
}

export function getCSV(answer, n = 1, step = 1, maxFrameMap = {}) {
  const items = extractAnswerFrameItems(answer);
  if (items.length === 0) return "";

  const parsedN = parseInt(n, 10) || 1;
  const parsedStep = parseInt(step, 10) || 1;

  // Helper to get max frame for a specific video ID
  const getVideoMaxBound = (vId) => {
    if (typeof maxFrameMap === "number") return maxFrameMap;
    if (maxFrameMap && typeof maxFrameMap[vId] === "number") return maxFrameMap[vId];
    return 999999;
  };

  // Extract QA answers (if any)
  const qaAnswers = answer.query_id === "QA" || answer.answer || answer.qa_answers ? extractQAAnswers(answer) : [];

  // ==========================================
  // SPECIAL HANDLING FOR TRAKE (Temporal Alignment)
  // Format per line: <video_id>, <frame_id_1>, <frame_id_2>, ..., <frame_id_n>
  // ==========================================
  if (answer.query_id === "TRAKE") {
    const trakeLines = [];
    const sequences = extractAnswerSequences(answer);
    if (sequences.length === 0) return "";

    const targetTotalRows = Math.max(parsedN, sequences.length);

    // Phase 1: Base Anchors of ALL Candidate Sequences
    for (const v of sequences) {
      const cleanFrames = v.frames.map((f) => formatCleanInteger(f)).join(",");
      trakeLines.push(`${v.video_id},${cleanFrames}`);
      if (trakeLines.length >= targetTotalRows) break;
    }

    let kMultiplier = 1;
    const maxEvents = Math.max(...sequences.map((v) => v.frames.length));

    while (trakeLines.length < targetTotalRows && kMultiplier <= 50) {
      const currentOffset = kMultiplier * parsedStep;

      // Phase 2a: Global Shift ALL -offset
      for (const v of sequences) {
        if (trakeLines.length >= targetTotalRows) break;
        const shifted = v.frames.map((f) => formatCleanInteger(Math.max(0, f - currentOffset))).join(",");
        trakeLines.push(`${v.video_id},${shifted}`);
      }

      // Phase 2b: Global Shift ALL +offset
      for (const v of sequences) {
        if (trakeLines.length >= targetTotalRows) break;
        const maxF = getVideoMaxBound(v.video_id);
        const shifted = v.frames.map((f) => formatCleanInteger(Math.min(maxF, f + currentOffset))).join(",");
        trakeLines.push(`${v.video_id},${shifted}`);
      }

      // Phase 3: Single-Event Jitters (Iterate event indices backwards from last to first)
      for (let eIdx = maxEvents - 1; eIdx >= 0; eIdx--) {
        if (trakeLines.length >= targetTotalRows) break;

        // Minus shift for Event eIdx
        for (const v of sequences) {
          if (trakeLines.length >= targetTotalRows) break;
          if (eIdx < v.frames.length) {
            const copy = [...v.frames];
            copy[eIdx] = Math.max(0, copy[eIdx] - currentOffset);
            const lineStr = copy.map((f) => formatCleanInteger(f)).join(",");
            trakeLines.push(`${v.video_id},${lineStr}`);
          }
        }

        // Plus shift for Event eIdx
        for (const v of sequences) {
          if (trakeLines.length >= targetTotalRows) break;
          if (eIdx < v.frames.length) {
            const maxF = getVideoMaxBound(v.video_id);
            const copy = [...v.frames];
            copy[eIdx] = Math.min(maxF, copy[eIdx] + currentOffset);
            const lineStr = copy.map((f) => formatCleanInteger(f)).join(",");
            trakeLines.push(`${v.video_id},${lineStr}`);
          }
        }
      }

      kMultiplier++;
    }

    return trakeLines.join("\n");
  }

  const totalSelectedFrames = items.length;
  const targetTotalRows = Math.max(parsedN, totalSelectedFrames);

  // Group items by video_id while maintaining video ordering
  const videoMap = new Map();
  items.forEach((item) => {
    if (!videoMap.has(item.video_id)) {
      videoMap.set(item.video_id, []);
    }
    videoMap.get(item.video_id).push(item.frame_counter);
  });

  const videos = Array.from(videoMap.entries()).map(([vId, frames]) => ({
    video_id: vId,
    frames: frames,
  }));

  // Build flat ordered list of all frame items for round-robin iteration
  const maxFramesPerVideo = videos.length > 0 ? Math.max(...videos.map((v) => v.frames.length)) : 0;
  const frameItems = [];
  for (let fIdx = 0; fIdx < maxFramesPerVideo; fIdx++) {
    for (const v of videos) {
      if (fIdx < v.frames.length) {
        frameItems.push({ video_id: v.video_id, center: v.frames[fIdx] });
      }
    }
  }

  // Track branch states per frame item
  const branchStates = frameItems.map((item) => ({
    subActive: true,
    addActive: true,
    lastSub: item.center,
    lastAdd: item.center,
  }));

  const lines = [];

  const pushFrameLines = (vId, calcFrame) => {
    const cleanFrameStr = formatCleanInteger(calcFrame);
    if (qaAnswers.length > 0) {
      for (const ansItem of qaAnswers) {
        lines.push(`${vId},${cleanFrameStr},${ansItem}`);
        if (lines.length >= targetTotalRows) break;
      }
    } else {
      lines.push(`${vId},${cleanFrameStr}`);
    }
  };

  // Round 0: Output ALL center frames in round-robin order
  for (const item of frameItems) {
    pushFrameLines(item.video_id, item.center);
    if (lines.length >= targetTotalRows) break;
  }

  // Subsequent rounds alternate: full sub round, then full add round
  while (lines.length < targetTotalRows) {
    // Check if ANY branch across ALL frame items is still active
    let anyActive = false;
    for (const state of branchStates) {
      if (state.subActive || state.addActive) {
        anyActive = true;
        break;
      }
    }
    if (!anyActive) break; // All frames exhausted both branches -> stop!

    // --- Sub round: iterate ALL frame items with subtraction ---
    let subRoundProduced = false;
    for (let i = 0; i < frameItems.length; i++) {
      if (lines.length >= targetTotalRows) break;
      const item = frameItems[i];
      const state = branchStates[i];
      if (!state.subActive) continue;

      const maxFrameForVideo = getVideoMaxBound(item.video_id);
      const nextSub = state.lastSub - parsedStep;
      if (nextSub <= 0) {
        pushFrameLines(item.video_id, 0);
        state.subActive = false; // Permanently terminate subtraction branch for this frame!
      } else {
        pushFrameLines(item.video_id, nextSub);
        state.lastSub = nextSub;
      }
      subRoundProduced = true;
    }

    if (lines.length >= targetTotalRows) break;

    // --- Add round: iterate ALL frame items with addition ---
    let addRoundProduced = false;
    for (let i = 0; i < frameItems.length; i++) {
      if (lines.length >= targetTotalRows) break;
      const item = frameItems[i];
      const state = branchStates[i];
      if (!state.addActive) continue;

      const maxFrameForVideo = getVideoMaxBound(item.video_id);
      const nextAdd = state.lastAdd + parsedStep;
      if (nextAdd >= maxFrameForVideo) {
        pushFrameLines(item.video_id, maxFrameForVideo);
        state.addActive = false; // Permanently terminate addition branch for this frame!
      } else {
        pushFrameLines(item.video_id, nextAdd);
        state.lastAdd = nextAdd;
      }
      addRoundProduced = true;
    }

    // Safety: if neither round produced anything, all branches are done
    if (!subRoundProduced && !addRoundProduced) break;
  }

  return lines.join("\n");
}

export async function getCSVAsync(answer, n = 1, step = 1) {
  const items = extractAnswerFrameItems(answer);
  if (items.length === 0) return "";
  const uniqueVids = [...new Set(items.map((it) => it.video_id))];
  const maxFrameMap = {};
  await Promise.all(
    uniqueVids.map(async (vId) => {
      maxFrameMap[vId] = await getVideoMaxFrame(vId);
    })
  );
  return getCSV(answer, n, step, maxFrameMap);
}

export async function exportAllAnswersCSV(answers, n = 1, step = 1) {
  if (!answers || !answers.length) return "";
  let csvContent = "";
  for (const answer of answers) {
    if (csvContent !== "") csvContent += "\n";
    csvContent += await getCSVAsync(answer, n, step);
  }
  return csvContent;
}

export async function exportZipAllAnswers(answers, n = 1, step = 1) {
  if (!answers || !answers.length) return null;

  const zip = new JSZip();
  const usedFilenames = new Map();

  for (let idx = 0; idx < answers.length; idx++) {
    const answer = answers[idx];
    const csvContent = await getCSVAsync(answer, n, step);
    if (!csvContent) continue;

    let baseName = "";
    if (answer.custom_filename && answer.custom_filename.trim()) {
      baseName = answer.custom_filename.trim().replace(/\.csv$/i, "");
    } else {
      const vId = answer.video_id || "answer";
      baseName = `answer_${vId}_${idx + 1}`;
    }

    let fileName = `${baseName}.csv`;
    if (usedFilenames.has(baseName)) {
      const count = usedFilenames.get(baseName) + 1;
      usedFilenames.set(baseName, count);
      fileName = `${baseName}_${count}.csv`;
    } else {
      usedFilenames.set(baseName, 1);
    }

    zip.file(fileName, csvContent);
  }

  return await zip.generateAsync({ type: "blob" });
}

