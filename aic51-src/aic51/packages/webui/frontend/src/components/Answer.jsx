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
import { getCSV, getAnswersByIds } from "../services/answer.js";
import { getBlob, downloadFile } from "../utils/files.js";
import { getFrameInfo } from "../services/search.js";

const QUERY_ID_OPTIONS = [
  { id: "TKIS", name: "TKIS" },
  { id: "VKIS", name: "VKIS" },
  { id: "QA", name: "QA" },
  { id: "TRAKE", name: "TRAKE" },
];

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
  const [videoIdValue, setVideoIdValue] = useState("");
  const [frameCounterValue, setFrameCounterValue] = useState("");

  const selectedFramesText =
    selected.length > 0
      ? selected
          .map((frameId) => {
            const [, frameCounter] = frameId.split("#");
            return frameCounter;
          })
          .join(",")
      : "";

  const selectedVideoId = selected.length > 0 ? selected[0].split("#")[0] : "";

  useEffect(() => {
    if (selected.length > 0) {
      setVideoIdValue(selectedVideoId);
      setFrameCounterValue(selectedFramesText);
    } else {
      setVideoIdValue("");
      setFrameCounterValue("");
    }
  }, [selected, selectedVideoId, selectedFramesText]);

  return (
    <fetcher.Form action="/answers" method="POST" className="w-full mb-1.5">
      <div className="p-2 w-full flex flex-col gap-1.5 bg-lime-100 border border-lime-300 rounded-lg shadow-sm overflow-hidden box-border">
        <div className="grid grid-cols-3 gap-1 w-full min-w-0">
          <select
            required
            name="query_id"
            value={selectedQueryId}
            onChange={(e) => setSelectedQueryId(e.target.value)}
            className="w-full min-w-0 py-1 px-1 text-xs bg-white border border-gray-400 rounded focus:outline-none font-semibold truncate"
          >
            {availableQueryIds.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>

          <input
            required
            type="text"
            name="video_id"
            placeholder="Video ID"
            autoComplete="off"
            value={videoIdValue}
            onChange={(e) => setVideoIdValue(e.target.value)}
            className="w-full min-w-0 py-1 px-1.5 text-xs bg-white border border-gray-400 rounded focus:outline-none font-semibold truncate"
          />

          <input
            required
            type="text"
            name="frame_counter"
            placeholder="Frame Counter"
            autoComplete="off"
            value={frameCounterValue}
            onChange={(e) => setFrameCounterValue(e.target.value)}
            className="w-full min-w-0 py-1 px-1.5 text-xs bg-white border border-gray-400 rounded focus:outline-none font-semibold truncate"
          />
        </div>

        {selected.length > 0 && (
          <div className="text-[9px] text-lime-900 font-mono leading-tight">
            Form values are synchronized from the visually staged frames. Manual edits remain possible.
          </div>
        )}

        {selectedQueryId === "QA" && (
          <input
            type="text"
            name="answer"
            placeholder="Answer (Only required for QA)"
            autoComplete="off"
            className="w-full min-w-0 py-1 px-1.5 text-xs bg-white border border-gray-400 rounded focus:outline-none font-semibold animate-fadeIn"
          />
        )}

        <button
          type="submit"
          className="w-full py-1.5 bg-sky-100 hover:bg-sky-200 active:bg-sky-300 border border-gray-700 rounded-lg text-xs font-bold text-gray-800 shadow-sm transition-colors"
        >
          Add
        </button>
      </div>
    </fetcher.Form>
  );
}

function SelectedFramesPreview() {
  const {
    selected,
    selectionNotice,
    removeSelected,
    clearSelected,
    moveSelected,
    clearSelectionNotice,
  } = useSelected();
  const playVideo = usePlayVideo();

  if (selected.length === 0) return null;

  const handlePlayFrame = (frameId) => {
    if (!frameId) return;
    const parts = frameId.split("#");
    const vId = parts[0];
    const fId = parts[1] || "0";
    if (vId) {
      getFrameInfo(vId, fId)
        .then((frameInfo) => {
          playVideo(frameInfo, fId);
        })
        .catch((err) => console.error("Failed to play selected frame:", err));
    }
  };

  return (
    <div className="p-1.5 bg-green-50 border border-green-300 rounded mb-1 text-xs w-full overflow-hidden">
      <div className="font-bold text-green-900 mb-1 text-[11px] flex justify-between items-center gap-2">
        <span>Selected Frames ({selected.length})</span>
        <div className="flex items-center gap-1">
          <span className="text-[9px] text-green-700 font-normal">Click frame to verify</span>
          <button
            type="button"
            onClick={clearSelected}
            className="px-1.5 py-0.5 text-[9px] bg-white hover:bg-red-50 text-red-700 border border-red-300 rounded font-bold"
          >
            Clear
          </button>
        </div>
      </div>

      {selectionNotice && (
        <div className="mb-1 flex items-start justify-between gap-1 bg-amber-50 border border-amber-300 text-amber-900 rounded px-1.5 py-1 text-[9px] leading-tight">
          <span>{selectionNotice}</span>
          <button
            type="button"
            onClick={clearSelectionNotice}
            className="font-bold text-amber-700 hover:text-amber-900"
            title="Dismiss"
          >
            ✕
          </button>
        </div>
      )}

      <div className="flex flex-col gap-1 max-h-28 overflow-y-auto">
        {selected.map((frameId, index) => (
          <div
            key={frameId}
            className="flex items-center gap-1 bg-white text-green-900 border border-green-300 rounded px-1 py-0.5 text-[10px] font-mono shadow-sm min-w-0"
          >
            <span className="font-bold text-gray-400 text-[9px] w-5 shrink-0 text-center">
              #{index + 1}
            </span>
            <button
              type="button"
              onClick={() => handlePlayFrame(frameId)}
              className="truncate text-left hover:underline font-bold flex-1 min-w-0"
              title="Open this staged frame in verification player"
            >
              {frameId}
            </button>
            <button
              type="button"
              onClick={() => moveSelected(index, index - 1)}
              disabled={index === 0}
              className="w-5 h-5 border border-gray-300 rounded text-gray-600 disabled:text-gray-300 disabled:bg-gray-50 hover:bg-gray-100 shrink-0"
              title="Move earlier"
            >
              ↑
            </button>
            <button
              type="button"
              onClick={() => moveSelected(index, index + 1)}
              disabled={index === selected.length - 1}
              className="w-5 h-5 border border-gray-300 rounded text-gray-600 disabled:text-gray-300 disabled:bg-gray-50 hover:bg-gray-100 shrink-0"
              title="Move later"
            >
              ↓
            </button>
            <button
              type="button"
              onClick={() => removeSelected(frameId)}
              className="w-5 h-5 text-red-500 hover:text-red-700 font-bold shrink-0 hover:bg-red-100 rounded"
              title="Remove frame"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
      <div className="mt-1 text-[9px] text-green-800 font-mono leading-tight">
        Order is preserved in the staging UI. Remote contest submission remains single-point until its payload rules are separately verified.
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
  const hasVerifiedTime = Number.isFinite(Number(answer.time));

  const handleOnPlay = (e) => {
    e.stopPropagation();
    try {
      const fId =
        answer.frame_id ||
        (Array.isArray(answer.frame_counter)
          ? answer.frame_counter[0]
          : answer.frame_counter);
      getFrameInfo(answer.video_id, fId).then((frameInfo) => {
        playVideo(frameInfo, fId);
      });
    } catch (err) {
      console.error(err);
    }
  };

  const handleOnFind = (e) => {
    e.stopPropagation();
    const currentParams = Object.fromEntries(searchParams);
    const filteredParams = Object.keys(currentParams)
      .filter((k) => k !== "q" && k !== "offset")
      .reduce((obj, key) => {
        obj[key] = currentParams[key];
        return obj;
      }, {});

    const fId =
      answer.frame_id ||
      (Array.isArray(answer.frame_counter)
        ? answer.frame_counter[0]
        : answer.frame_counter);
    submit(
      {
        ...filteredParams,
        id: `${answer.video_id}#${fId}`,
      },
      { action: "/similar" }
    );
  };

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
        <div className="p-1.5 w-full flex flex-col gap-1 bg-lime-100 border border-lime-300 rounded text-xs">
          <div className="grid grid-cols-2 gap-1">
            <select
              required
              name="query_id"
              defaultValue={answer.query_id || "TKIS"}
              className="p-1 border rounded bg-white"
            >
              {QUERY_ID_OPTIONS.map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.name}
                </option>
              ))}
            </select>
            <input
              required
              type="text"
              name="video_id"
              placeholder="Video ID"
              autoComplete="off"
              defaultValue={answer.video_id}
              className="p-1 border rounded"
            />
          </div>
          <input
            required
            type="text"
            name="frame_counter"
            placeholder="Frame Counter"
            autoComplete="off"
            defaultValue={
              Array.isArray(answer.frame_counter)
                ? answer.frame_counter.join(",")
                : answer.frame_counter
            }
            className="w-full p-1 border rounded"
          />
          {answer.query_id === "QA" && (
            <input
              type="text"
              name="answer"
              placeholder="Answer"
              autoComplete="off"
              defaultValue={answer.answer}
              className="w-full p-1 border rounded"
            />
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

  const frameStr = Array.isArray(answer.frame_counter)
    ? answer.frame_counter.join(",")
    : answer.frame_id || answer.frame_counter;

  return (
    <div
      className={classNames(
        "relative w-full flex flex-row justify-between items-center p-1.5 rounded border text-xs cursor-pointer transition-colors mb-1 overflow-hidden",
        {
          "bg-purple-200 border-purple-400": inList,
          "bg-blue-100 border-blue-300 font-bold": !inList && selected,
          "bg-white border-gray-200 hover:bg-gray-100": !inList && !selected,
        }
      )}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
      onClick={() => onClick(answer)}
    >
      <div id="answer-description" className="flex flex-row items-center gap-1.5 text-[11px] font-mono truncate min-w-0 pr-1">
        <span className="font-bold text-gray-500 bg-gray-100 border border-gray-300 px-1 py-0.5 rounded text-[10px] shrink-0 font-mono">
          #{index}
        </span>
        <div className="flex flex-col truncate min-w-0">
          <span className="font-bold text-gray-800 truncate">{answer.query_id || "Answer"}</span>
          <span className="text-gray-500 text-[9px] truncate">{answer.video_id} #{frameStr}</span>
        </div>
      </div>

      <div
        id="answer-option"
        className="flex flex-row items-center gap-0.5 shrink-0"
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
          className={`p-0.5 rounded select-none ${
            hasVerifiedTime
              ? "hover:bg-blue-200 cursor-pointer"
              : "opacity-30 cursor-not-allowed"
          }`}
          src={SubmitButton}
          width="18em"
          draggable="false"
          alt="Submit"
          title={
            hasVerifiedTime
              ? "Submit this verified single-point answer to AIC server"
              : "No verified timestamp on this staged answer; verify a frame and submit from the player"
          }
          onClick={() => {
            if (hasVerifiedTime) onSubmitAnswer(answer);
          }}
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
          src={PlayButton}
          width="18em"
          draggable="false"
          alt="Play"
          title="Play video"
          onClick={handleOnPlay}
        />
        <img
          className="hover:bg-blue-200 p-0.5 rounded cursor-pointer select-none"
          src={FindButton}
          width="18em"
          draggable="false"
          alt="Find"
          title="Find similar"
          onClick={handleOnFind}
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

      {showTooltip && (
        <div className="absolute top-0 right-0 z-30 bg-slate-900 text-white text-[10px] p-1.5 rounded shadow-lg pointer-events-none border border-slate-700 opacity-95 animate-fadeIn">
          <div><strong>Task:</strong> {answer.query_id}</div>
          <div><strong>Video:</strong> {answer.video_id}</div>
          <div><strong>Frames:</strong> {frameStr}</div>
          {answer.answer && <div><strong>Ans:</strong> {answer.answer}</div>}
          {!hasVerifiedTime && <div className="text-amber-300">Remote submit unavailable: no verified timestamp.</div>}
        </div>
      )}
    </div>
  );
}

export default function AnswerSidebar() {
  const { submitAnswer } = useContext(AuthContext);
  const fetcher = useFetcher({ key: "answers" });
  const [selected, setSelected] = useState(null);
  const [downloadList, setDownloadList] = useState([]);

  const [downloadN, setDownloadN] = useState(1);
  const [downloadStep, setDownloadStep] = useState(1);

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

  const handleDownloadSingle = (answer) => {
    const csvContent = getCSV(answer, downloadN, downloadStep);
    const blob = getBlob(csvContent, "text/csv");
    downloadFile(blob, `answer_${answer.video_id}_${Date.now()}.csv`);
  };

  const handleDownloadAnswersCSV = async () => {
    if (downloadList.length === 0) return;

    const selectedAnswers = await getAnswersByIds(downloadList);
    let csvContent = "";

    for (const answer of selectedAnswers) {
      if (csvContent !== "") csvContent += "\n";
      csvContent += getCSV(answer, downloadN, downloadStep);
    }

    const blob = getBlob(csvContent, "text/csv");
    downloadFile(blob, `submission_answers_${Date.now()}.csv`);
  };

  return (
    <div className="w-full flex flex-col gap-1 p-1 box-border overflow-hidden">
      <div className="flex items-center justify-between bg-blue-50 border border-blue-200 rounded p-1.5 text-xs mb-1">
        <div className="flex items-center gap-1.5 font-bold text-gray-700">
          <label htmlFor="n-input" className="text-[11px]">N:</label>
          <input
            id="n-input"
            type="number"
            min="1"
            max="1000"
            value={downloadN}
            onChange={(e) => setDownloadN(parseInt(e.target.value, 10) || 1)}
            className="w-16 px-1 py-0.5 text-xs border border-gray-300 rounded font-mono font-bold bg-white text-center [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
          />

          <label htmlFor="step-input" className="text-[11px] ml-1">STEP:</label>
          <input
            id="step-input"
            type="number"
            min="1"
            max="1000"
            value={downloadStep}
            onChange={(e) => setDownloadStep(parseInt(e.target.value, 10) || 1)}
            className="w-16 px-1 py-0.5 text-xs border border-gray-300 rounded font-mono font-bold bg-white text-center [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
          />
        </div>

        {downloadList.length > 0 && (
          <button
            onClick={handleDownloadAnswersCSV}
            className="px-2 py-0.5 bg-green-600 hover:bg-green-700 text-white font-bold rounded text-xs shadow-sm"
          >
            CSV ({downloadList.length})
          </button>
        )}
      </div>

      <AnswerHeader />
      <SelectedFramesPreview />

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
