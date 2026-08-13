import { useFetcher, useSubmit, useSearchParams } from "react-router-dom";
import { useState, useEffect, useContext } from "react";
import classNames from "classnames";

import FindButton from "../assets/search-btn.svg";
import PlayButton from "../assets/play-btn.svg";
import DeleteButton from "../assets/delete-btn.svg";
import EditButton from "../assets/edit-btn.svg";
import DownloadButton from "../assets/download-btn.svg";
import SubmitButton from "../assets/upload-btn.svg";

import { usePlayVideo } from "./VideoPlayer.jsx";
import { useSelected } from "./SelectedProvider.jsx";
import { AuthContext } from "./AuthProvider.jsx";
import { getCSV, getCSVAsync, getAnswersByIds, extractAnswerFrameItems, extractQAAnswers, clearAllAnswers } from "../services/answer.js";
import { getBlob, downloadFile } from "../utils/files.js";
import { getFrameInfo } from "../services/search.js";

const QUERY_ID_OPTIONS = [
  { id: "TKIS", name: "TKIS" },
  { id: "VKIS", name: "VKIS" },
  { id: "QA", name: "QA" },
  { id: "TRAKE", name: "TRAKE" },
];

function getGroupedVideoRows(rawSelectedList, defaultVideoId = "", defaultFrameCounter = "") {
  const map = new Map();
  if (Array.isArray(rawSelectedList) && rawSelectedList.length > 0) {
    rawSelectedList.forEach((itemStr) => {
      const parts = String(itemStr).split("#");
      if (parts.length >= 2) {
        const vId = parts[0].trim();
        const fId = parts[1].trim();
        if (vId && fId && vId !== "undefined" && vId !== "null") {
          if (!map.has(vId)) map.set(vId, []);
          if (!map.get(vId).includes(fId)) map.get(vId).push(fId);
        }
      }
    });
  }

  if (map.size === 0) {
    const vIds = String(defaultVideoId || "")
      .split(",")
      .map((v) => v.trim())
      .filter((v) => v && v !== "undefined" && v !== "null");
    const fIds = (Array.isArray(defaultFrameCounter) ? defaultFrameCounter : String(defaultFrameCounter || "").split(","))
      .map((f) => String(f).trim())
      .filter(Boolean);

    if (vIds.length === fIds.length && vIds.length > 0) {
      for (let i = 0; i < vIds.length; i++) {
        if (!map.has(vIds[i])) map.set(vIds[i], []);
        map.get(vIds[i]).push(fIds[i]);
      }
    } else if (vIds.length > 0 && fIds.length > 0) {
      for (let i = 0; i < fIds.length; i++) {
        const vId = vIds[i] || vIds[0];
        if (!map.has(vId)) map.set(vId, []);
        map.get(vId).push(fIds[i]);
      }
    }
  }

  if (map.size === 0) {
    return [{ video_id: "", frames: "" }];
  }

  return Array.from(map.entries()).map(([vId, frames]) => ({
    video_id: vId,
    frames: frames.join(", "),
  }));
}

function AnswerHeader() {
  const { evaluationIds } = useContext(AuthContext);
  const fetcher = useFetcher({ key: "answers" });
  const { selected } = useSelected();

  const availableQueryIds =
    evaluationIds && evaluationIds.length > 0
      ? evaluationIds
      : QUERY_ID_OPTIONS;

  const [selectedQueryId, setSelectedQueryId] = useState(
    availableQueryIds[0]?.id || "TKIS"
  );

  const [videoRows, setVideoRows] = useState(() => getGroupedVideoRows(selected));
  const [qaAnswers, setQaAnswers] = useState([""]);

  useEffect(() => {
    setVideoRows(getGroupedVideoRows(selected));
  }, [selected.join(";")]);

  const handleRowChange = (idx, field, value) => {
    setVideoRows((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], [field]: value };
      return next;
    });
  };

  const handleAddRow = () => {
    setVideoRows((prev) => [...prev, { video_id: "", frames: "" }]);
  };

  const handleRemoveRow = (idx) => {
    setVideoRows((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleQaAnswerChange = (idx, val) => {
    setQaAnswers((prev) => {
      const next = [...prev];
      next[idx] = val;
      return next;
    });
  };

  const handleAddQaAnswer = () => {
    setQaAnswers((prev) => [...prev, ""]);
  };

  const handleRemoveQaAnswer = (idx) => {
    setQaAnswers((prev) => prev.filter((_, i) => i !== idx));
  };

  const combinedRawSelected = videoRows
    .flatMap((row) => {
      const vId = row.video_id.trim();
      const fList = row.frames.split(",").map((f) => f.trim()).filter(Boolean);
      return fList.map((fId) => `${vId}#${fId}`);
    })
    .filter((str) => str.includes("#") && !str.startsWith("#") && !str.endsWith("#"))
    .join(";");

  const combinedVideoId = videoRows
    .map((row) => row.video_id.trim())
    .filter(Boolean)
    .join(",");

  const combinedFrameCounter = videoRows
    .flatMap((row) => row.frames.split(",").map((f) => f.trim()).filter(Boolean))
    .join(",");

  const combinedQaAnswers = qaAnswers.filter((a) => a.trim().length > 0).join("|");
  const combinedAnswerDisplay = qaAnswers.filter((a) => a.trim().length > 0).join(" | ");

  return (
    <fetcher.Form action="/answers" method="POST" className="w-full mb-1.5">
      <input type="hidden" name="raw_selected" value={combinedRawSelected} />
      <input type="hidden" name="video_id" value={combinedVideoId} />
      <input type="hidden" name="frame_counter" value={combinedFrameCounter} />
      <input type="hidden" name="qa_answers" value={combinedQaAnswers} />
      <input type="hidden" name="answer" value={combinedAnswerDisplay} />

      <div className="p-2 w-full flex flex-col gap-1.5 bg-lime-100 border border-lime-300 rounded-lg shadow-sm box-border">
        {/* Row 1: Query ID Select */}
        <div className="flex items-center gap-1.5 w-full">
          <label className="text-xs font-bold text-gray-700 shrink-0">Task:</label>
          <select
            required
            name="query_id"
            value={selectedQueryId}
            onChange={(e) => setSelectedQueryId(e.target.value)}
            className="flex-1 py-1 px-1.5 text-xs bg-white border border-gray-400 rounded focus:outline-none font-semibold truncate"
          >
            {availableQueryIds.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
        </div>

        {/* Dynamic Video Rows - Each Video ID on its own row with frames beside it */}
        <div className="flex flex-col gap-1 max-h-36 overflow-y-auto pr-0.5">
          {videoRows.map((row, idx) => (
            <div key={idx} className="flex items-center gap-1 w-full text-xs">
              <input
                required
                type="text"
                placeholder="Video ID"
                value={row.video_id}
                onChange={(e) => handleRowChange(idx, "video_id", e.target.value)}
                className="w-2/5 py-1 px-1.5 text-xs bg-white border border-gray-400 rounded focus:outline-none font-semibold font-mono truncate"
              />
              <input
                required
                type="text"
                placeholder="Frames (e.g. 039124, 020893)"
                value={row.frames}
                onChange={(e) => handleRowChange(idx, "frames", e.target.value)}
                className="w-3/5 py-1 px-1.5 text-xs bg-white border border-gray-400 rounded focus:outline-none font-semibold font-mono truncate"
              />
              {videoRows.length > 1 && (
                <button
                  type="button"
                  onClick={() => handleRemoveRow(idx)}
                  className="text-red-500 hover:text-red-700 font-bold px-1 hover:bg-red-100 rounded text-xs shrink-0"
                  title="Remove video row"
                >
                  ✕
                </button>
              )}
            </div>
          ))}
        </div>

        {/* Add Video Row Button */}
        <div className="flex justify-between items-center">
          <button
            type="button"
            onClick={handleAddRow}
            className="text-[10px] text-blue-700 hover:underline font-bold"
          >
            + Add Video Row
          </button>
        </div>

        {/* QA Multi-Answers Section - PLACED BELOW Add Video Row */}
        {selectedQueryId === "QA" && (
          <div className="flex flex-col gap-1 border-t border-lime-300 pt-1.5 animate-fadeIn">
            <label className="text-[11px] font-bold text-gray-700">QA Answers:</label>
            <div className="flex flex-col gap-1 max-h-28 overflow-y-auto pr-0.5">
              {qaAnswers.map((ans, idx) => (
                <div key={idx} className="flex items-center gap-1 w-full text-xs">
                  <input
                    type="text"
                    placeholder={`Answer #${idx + 1}`}
                    value={ans}
                    onChange={(e) => handleQaAnswerChange(idx, e.target.value)}
                    className="flex-1 py-1 px-1.5 text-xs bg-white border border-gray-400 rounded focus:outline-none font-semibold truncate"
                  />
                  {qaAnswers.length > 1 && (
                    <button
                      type="button"
                      onClick={() => handleRemoveQaAnswer(idx)}
                      className="text-red-500 hover:text-red-700 font-bold px-1 hover:bg-red-100 rounded text-xs shrink-0"
                      title="Remove answer"
                    >
                      ✕
                    </button>
                  )}
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={handleAddQaAnswer}
              className="text-[10px] text-blue-700 hover:underline font-bold text-left self-start mt-0.5"
            >
              + Add Answer for QA
            </button>
          </div>
        )}

        <button
          type="submit"
          className="w-full py-1.5 bg-sky-100 hover:bg-sky-200 active:bg-sky-300 border border-gray-700 rounded-lg text-xs font-bold text-gray-800 shadow-sm transition-colors mt-0.5"
        >
          Add
        </button>
      </div>
    </fetcher.Form>
  );
}

function SelectedFramesPreview() {
  const { selected, removeSelected } = useSelected();
  const playVideo = usePlayVideo();

  if (selected.length === 0) return null;

  const handlePlayFrame = (frameId) => {
    if (!frameId) return;
    let vId = "";
    let fId = "0";

    if (typeof frameId === "string") {
      if (frameId.includes("#")) {
        const parts = frameId.split("#");
        vId = parts[0];
        fId = parts[1] || "0";
      } else {
        fId = frameId;
      }
    } else if (typeof frameId === "object" && frameId !== null) {
      vId = frameId.video_id;
      fId = frameId.frame_id || frameId.frame_counter || "0";
    }

    if (!vId || vId === "undefined" || vId === "null") {
      const foundWithVid = selected.find(
        (item) => typeof item === "string" && item.includes("#") && !item.startsWith("undefined") && !item.startsWith("null")
      );
      if (foundWithVid) {
        vId = foundWithVid.split("#")[0];
      }
    }

    if (vId && vId !== "undefined" && vId !== "null") {
      playVideo(vId, fId);
    }
  };

  return (
    <div className="p-1.5 bg-green-50 border border-green-300 rounded mb-1 text-xs w-full overflow-hidden">
      <div className="font-bold text-green-900 mb-1 text-[11px] flex justify-between items-center">
        <span>Selected Frames ({selected.length}):</span>
        <span className="text-[9px] text-green-700 font-normal">Click item to play</span>
      </div>
      <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
        {selected.map((frameId, index) => (
          <span
            key={frameId}
            onClick={() => handlePlayFrame(frameId)}
            className="inline-flex items-center gap-1 bg-white hover:bg-emerald-100 text-green-900 border border-green-400 hover:border-green-600 rounded px-1.5 py-0.5 text-[10px] font-mono cursor-pointer shadow-sm truncate max-w-full transition-colors group"
            title="Click to open video player"
          >
            <span className="font-bold text-gray-400 text-[9px]">#{index + 1}</span>
            <span className="truncate group-hover:underline font-bold">{frameId}</span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                removeSelected(frameId);
              }}
              className="text-red-500 hover:text-red-700 font-bold shrink-0 px-0.5 hover:bg-red-100 rounded"
              title="Remove frame"
            >
              ✕
            </button>
          </span>
        ))}
      </div>
    </div>
  );
}

function AnswerItem({
  index,
  answer,
  selected,
  onClick,
  inList,
  onDownload,
  onSubmitAnswer,
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [showTooltip, setShowTooltip] = useState(false);
  const submit = useSubmit();
  const [searchParams] = useSearchParams();
  const fetcher = useFetcher({ key: "answers" });
  const playVideo = usePlayVideo();

  const [editQueryId, setEditQueryId] = useState(answer.query_id || "TKIS");
  const [editQaAnswers, setEditQaAnswers] = useState(() => {
    const list = extractQAAnswers(answer);
    return list.length > 0 ? list : [""];
  });

  const [editRows, setEditRows] = useState(() =>
    getGroupedVideoRows(answer.raw_selected, answer.video_id, answer.frame_counter)
  );

  const handleEditRowChange = (idx, field, value) => {
    setEditRows((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], [field]: value };
      return next;
    });
  };

  const handleEditAddRow = () => {
    setEditRows((prev) => [...prev, { video_id: "", frames: "" }]);
  };

  const handleEditRemoveRow = (idx) => {
    setEditRows((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleEditQaAnswerChange = (idx, val) => {
    setEditQaAnswers((prev) => {
      const next = [...prev];
      next[idx] = val;
      return next;
    });
  };

  const handleEditAddQaAnswer = () => {
    setEditQaAnswers((prev) => [...prev, ""]);
  };

  const handleEditRemoveQaAnswer = (idx) => {
    setEditQaAnswers((prev) => prev.filter((_, i) => i !== idx));
  };

  const editRawSelected = editRows
    .flatMap((row) => {
      const vId = row.video_id.trim();
      const fList = row.frames.split(",").map((f) => f.trim()).filter(Boolean);
      return fList.map((fId) => `${vId}#${fId}`);
    })
    .filter((str) => str.includes("#") && !str.startsWith("#") && !str.endsWith("#"))
    .join(";");

  const editVideoId = editRows
    .map((row) => row.video_id.trim())
    .filter(Boolean)
    .join(",");

  const editFrameCounter = editRows
    .flatMap((row) => row.frames.split(",").map((f) => f.trim()).filter(Boolean))
    .join(",");

  const combinedEditQaAnswers = editQaAnswers.filter((a) => a.trim().length > 0).join("|");
  const combinedEditAnswerDisplay = editQaAnswers.filter((a) => a.trim().length > 0).join(" | ");

  const handleOnDelete = (e) => {
    e.stopPropagation();
    fetcher.submit(null, {
      method: "POST",
      action: `/answers/${answer.id}/delete`,
    });
  };

  if (isEditing) {
    return (
      <fetcher.Form
        action={`/answers/${answer.id}/edit`}
        method="POST"
        onSubmit={(e) => {
          e.preventDefault();
          fetcher.submit(e.currentTarget);
          setIsEditing(false);
        }}
        className="w-full mb-1"
      >
        <input type="hidden" name="raw_selected" value={editRawSelected} />
        <input type="hidden" name="video_id" value={editVideoId} />
        <input type="hidden" name="frame_counter" value={editFrameCounter} />
        <input type="hidden" name="qa_answers" value={combinedEditQaAnswers} />
        <input type="hidden" name="answer" value={combinedEditAnswerDisplay} />

        <div className="p-1.5 w-full flex flex-col gap-1.5 bg-lime-100 border border-lime-300 rounded text-xs">
          <div className="flex items-center gap-1.5 w-full">
            <label className="text-[11px] font-bold text-gray-700 shrink-0">Task:</label>
            <select
              required
              name="query_id"
              value={editQueryId}
              onChange={(e) => setEditQueryId(e.target.value)}
              className="flex-1 p-1 border rounded bg-white font-semibold"
            >
              {QUERY_ID_OPTIONS.map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1 max-h-36 overflow-y-auto">
            {editRows.map((row, idx) => (
              <div key={idx} className="flex items-center gap-1 w-full text-xs">
                <input
                  required
                  type="text"
                  placeholder="Video ID"
                  value={row.video_id}
                  onChange={(e) => handleEditRowChange(idx, "video_id", e.target.value)}
                  className="w-2/5 p-1 border rounded bg-white font-mono font-semibold truncate"
                />
                <input
                  required
                  type="text"
                  placeholder="Frames"
                  value={row.frames}
                  onChange={(e) => handleEditRowChange(idx, "frames", e.target.value)}
                  className="w-3/5 p-1 border rounded bg-white font-mono font-semibold truncate"
                />
                {editRows.length > 1 && (
                  <button
                    type="button"
                    onClick={() => handleEditRemoveRow(idx)}
                    className="text-red-500 hover:text-red-700 font-bold px-1 hover:bg-red-100 rounded shrink-0"
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>

          <button
            type="button"
            onClick={handleEditAddRow}
            className="text-[10px] text-blue-700 hover:underline font-bold text-left"
          >
            + Add Video Row
          </button>

          {/* QA Multi-Answers Section - PLACED BELOW Add Video Row */}
          {editQueryId === "QA" && (
            <div className="flex flex-col gap-1 border-t border-lime-300 pt-1.5 animate-fadeIn">
              <label className="text-[11px] font-bold text-gray-700">QA Answers:</label>
              <div className="flex flex-col gap-1 max-h-28 overflow-y-auto pr-0.5">
                {editQaAnswers.map((ans, idx) => (
                  <div key={idx} className="flex items-center gap-1 w-full text-xs">
                    <input
                      type="text"
                      placeholder={`Answer #${idx + 1}`}
                      value={ans}
                      onChange={(e) => handleEditQaAnswerChange(idx, e.target.value)}
                      className="flex-1 p-1 border rounded bg-white font-semibold truncate"
                    />
                    {editQaAnswers.length > 1 && (
                      <button
                        type="button"
                        onClick={() => handleEditRemoveQaAnswer(idx)}
                        className="text-red-500 hover:text-red-700 font-bold px-1 hover:bg-red-100 rounded text-xs shrink-0"
                      >
                        ✕
                      </button>
                    )}
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={handleEditAddQaAnswer}
                className="text-[10px] text-blue-700 hover:underline font-bold text-left self-start mt-0.5"
              >
                + Add Answer for QA
              </button>
            </div>
          )}

          <div className="flex gap-2 mt-1">
            <button
              type="submit"
              className="flex-1 py-1 bg-sky-200 hover:bg-sky-300 font-bold border border-gray-700 rounded"
            >
              Edit
            </button>
            <button
              type="button"
              onClick={() => setIsEditing(false)}
              className="flex-1 py-1 bg-red-600 hover:bg-red-700 text-white font-bold rounded"
            >
              Cancel
            </button>
          </div>
        </div>
      </fetcher.Form>
    );
  }

  const items = extractAnswerFrameItems(answer);
  const uniqueVideos = [...new Set(items.map((it) => it.video_id))].join(", ");
  const frameStr = items.map((it) => it.frame_counter).join(",");
  const displayVideoStr = uniqueVideos || answer.video_id;

  return (
    <div
      className={classNames(
        "relative w-full flex flex-row justify-between items-center p-1.5 rounded border text-xs cursor-pointer transition-colors mb-1 overflow-visible",
        {
          "bg-purple-200 border-purple-400": inList,
          "bg-blue-100 border-blue-300 font-bold": !inList && selected,
          "bg-white border-gray-200 hover:bg-gray-100": !inList && !selected,
        }
      )}
      onClick={() => onClick(answer)}
    >
      <div
        id="answer-description"
        className="relative flex flex-row items-center gap-1.5 text-[11px] font-mono truncate min-w-0 pr-1"
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        {/* Sequence Number STT Badge */}
        <span className="font-bold text-gray-500 bg-gray-100 border border-gray-300 px-1 py-0.5 rounded text-[10px] shrink-0 font-mono">
          #{index}
        </span>
        <div className="flex flex-col truncate min-w-0">
          <span className="font-bold text-gray-800 truncate">{answer.query_id || "Answer"}</span>
          <span className="text-gray-500 text-[9px] truncate">{displayVideoStr} #{frameStr}</span>
        </div>

        {/* Floating Tooltip - Positioned below description so action buttons remain untouched */}
        {showTooltip && (
          <div className="absolute top-full left-0 mt-1 z-50 bg-slate-900 text-white text-[10px] p-2 rounded-md shadow-xl pointer-events-none border border-slate-700 opacity-95 animate-fadeIn max-w-xs whitespace-normal break-all">
            <div><strong>Task:</strong> {answer.query_id}</div>
            <div><strong>Videos:</strong> {displayVideoStr}</div>
            <div><strong>Frames:</strong> {frameStr}</div>
            {answer.answer && <div><strong>Ans:</strong> {answer.answer}</div>}
          </div>
        )}
      </div>

      <div
        id="answer-option"
        className="flex flex-row items-center gap-0.5 shrink-0 z-10"
        onClick={(e) => e.stopPropagation()}
      >
        <img
          className="hover:bg-blue-200 p-0.5 rounded cursor-pointer select-none"
          src={EditButton}
          width="18em"
          draggable="false"
          alt="Edit"
          title="Edit answer"
          onClick={() => setIsEditing(true)}
        />
        <img
          className="hover:bg-blue-200 p-0.5 rounded cursor-pointer select-none"
          src={SubmitButton}
          width="18em"
          draggable="false"
          alt="Submit"
          title="Submit answer to AIC server"
          onClick={() => onSubmitAnswer(answer)}
        />
        <img
          className="hover:bg-blue-200 p-0.5 rounded cursor-pointer select-none"
          src={DownloadButton}
          width="18em"
          draggable="false"
          alt="Download"
          title="Download clean CSV"
          onClick={() => onDownload(answer)}
        />
        <img
          className="hover:bg-blue-200 p-0.5 rounded cursor-pointer select-none"
          src={DeleteButton}
          width="18em"
          draggable="false"
          alt="Delete"
          title="Delete answer"
          onClick={handleOnDelete}
        />
      </div>
    </div>
  );
}

export default function AnswerSidebar() {
  const { submitAnswer } = useContext(AuthContext);
  const fetcher = useFetcher({ key: "answers" });
  const [selected, setSelected] = useState(null);
  const [downloadList, setDownloadList] = useState([]);

  // Default N = 100, STEP = 50
  const [downloadN, setDownloadN] = useState(100);
  const [downloadStep, setDownloadStep] = useState(50);

  useEffect(() => {
    if (fetcher.state === "idle" && !fetcher.data) {
      fetcher.load("/answers");
    }
  }, [fetcher]);

  const handleOnClick = (answer) => {
    if (downloadList.includes(answer.id)) {
      setDownloadList(downloadList.filter((id) => id !== answer.id));
    } else {
      setDownloadList([...downloadList, answer.id]);
    }
  };

  const handleOnSubmitAnswer = async (a) => {
    if (submitAnswer) {
      submitAnswer(a);
    }
  };

  const handleClearAllAnswers = async () => {
    if (window.confirm("Are you sure you want to reset and clear all saved answers?")) {
      await clearAllAnswers();
      setDownloadList([]);
      fetcher.load("/answers");
    }
  };

  const handleDownloadSingle = async (answer) => {
    const csvContent = await getCSVAsync(answer, downloadN, downloadStep);
    const blob = getBlob(csvContent, "text/csv");
    downloadFile(blob, `answer_${answer.video_id}_${Date.now()}.csv`);
  };

  const handleDownloadAnswersCSV = async () => {
    if (downloadList.length === 0) return;

    const selectedAnswers = await getAnswersByIds(downloadList);
    let csvContent = "";

    for (const answer of selectedAnswers) {
      if (csvContent !== "") csvContent += "\n";
      csvContent += await getCSVAsync(answer, downloadN, downloadStep);
    }

    const blob = getBlob(csvContent, "text/csv");
    downloadFile(blob, `submission_answers_${Date.now()}.csv`);
  };

  return (
    <div className="w-full flex flex-col gap-1 p-1 box-border overflow-hidden">
      {/* N: and STEP: Parameters Header Bar */}
      <div className="flex items-center justify-between bg-blue-50 border border-blue-200 rounded p-1.5 text-xs mb-1">
        <div className="flex items-center gap-1.5 font-bold text-gray-700">
          <label htmlFor="n-input" className="text-[11px]">N:</label>
          <input
            id="n-input"
            type="number"
            min="1"
            max="5000"
            value={downloadN}
            onChange={(e) => setDownloadN(parseInt(e.target.value, 10) || 1)}
            className="w-14 px-1 py-0.5 text-xs border border-gray-300 rounded font-mono font-bold bg-white text-center [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
          />

          <label htmlFor="step-input" className="text-[11px] ml-1">STEP:</label>
          <input
            id="step-input"
            type="number"
            min="1"
            max="5000"
            value={downloadStep}
            onChange={(e) => setDownloadStep(parseInt(e.target.value, 10) || 1)}
            className="w-14 px-1 py-0.5 text-xs border border-gray-300 rounded font-mono font-bold bg-white text-center [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
          />
        </div>

        {downloadList.length > 0 && (
          <div className="flex items-center gap-1">
            <button
              onClick={handleDownloadAnswersCSV}
              className="px-2 py-0.5 bg-green-600 hover:bg-green-700 active:bg-green-800 text-white font-bold rounded text-xs shadow-sm transition-colors"
              title="Download selected CSV answers"
            >
              CSV ({downloadList.length})
            </button>
            <button
              onClick={() => setDownloadList([])}
              className="px-1.5 py-0.5 bg-gray-200 hover:bg-red-500 hover:text-white text-gray-700 font-bold rounded text-xs shadow-sm transition-colors"
              title="Clear selected answers"
            >
              Clear
            </button>
          </div>
        )}
      </div>

      {/* Answer Form */}
      <AnswerHeader />
      <SelectedFramesPreview />

      {/* Saved Answers Header with Reset All Button */}
      {fetcher.data && fetcher.data.length > 0 && (
        <div className="flex justify-between items-center px-1 py-0.5 text-[11px] font-bold text-gray-700">
          <span>Saved Answers ({fetcher.data.length}):</span>
          <button
            type="button"
            onClick={handleClearAllAnswers}
            className="text-[10px] text-red-600 hover:text-red-800 hover:underline font-semibold"
          >
            Reset All Answers
          </button>
        </div>
      )}

      {/* Answer List with Sequence Numbers STT */}
      <div className="flex flex-col max-h-56 overflow-y-auto pr-0.5">
        {fetcher.data && fetcher.data.length > 0 ? (
          fetcher.data
            .slice()
            .reverse()
            .map((answer, idx) => (
              <AnswerItem
                key={answer.id}
                index={idx + 1}
                answer={answer}
                selected={selected !== null && selected.id === answer.id}
                inList={downloadList.includes(answer.id)}
                onClick={handleOnClick}
                onDownload={handleDownloadSingle}
                onSubmitAnswer={handleOnSubmitAnswer}
              />
            ))
        ) : (
          <div className="text-xs text-gray-400 text-center py-3 italic border border-dashed rounded bg-white">
            No saved answers.
          </div>
        )}
      </div>
    </div>
  );
}