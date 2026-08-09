import { Form, useLoaderData, useNavigation, useSubmit } from "react-router-dom";
import { useEffect, useState } from "react";

import { search } from "../services/search.js";
import { FrameContainer, FrameItem } from "../components/Frame.jsx";
import { usePlayVideo } from "../components/VideoPlayer.jsx";
import { AdvanceQueryContainer } from "../components/AdvanceQuery.jsx";
import { useSelected } from "../components/SelectedProvider.jsx";
import { getTimelineColor } from "../utils/timelineColors.js";
import SpinIcon from "../assets/spin.svg";
import {
  clearQueryHistory,
  getResultTotal,
  groupTemporalCandidates,
  loadQueryHistory,
  rememberQuery,
  saveQueryHistory,
  serializeQueryState,
} from "../utils/queryState.js";
import { getShortcutAction } from "../utils/keyboardShortcuts.js";

import {
  limitOptions,
  nprobeOption,
  temporal_k_default,
  ocr_weight_default,
  asr_weight_default,
  max_interval_default,
} from "../resources/options.js";

function appendVideoFilters(query, includeVideo) {
  const include = includeVideo
    ? `[video:${includeVideo.split(",").map((item) => item.trim()).filter(Boolean).join(",")}]`
    : "";
  return [query, include].filter(Boolean).join(" ").trim();
}

export async function loader({ request }) {
  const url = new URL(request.url);
  const searchParams = url.searchParams;
  const q = searchParams.get("q") || "";
  const include_video = searchParams.get("include_video") || "";

  const params = {
    limit: searchParams.get("limit") || limitOptions[0],
    nprobe: searchParams.get("nprobe") || nprobeOption[0],
    temporal_k: searchParams.get("temporal_k") || temporal_k_default,
    ocr_weight: searchParams.get("ocr_weight") || ocr_weight_default,
    asr_weight: searchParams.get("asr_weight") || asr_weight_default,
    max_interval: searchParams.get("max_interval") || max_interval_default,
    target_features: searchParams.get("target_features") || "",
    auto_translate: searchParams.get("auto_translate") || "",
    include_video,
  };

  if (!q) {
    return { query: {}, params, selected: undefined, offset: 0, data: { total: 0, frames: [] } };
  }

  try {
    const response = await search(
      appendVideoFilters(q.replace(/[|\\]/g, ";"), include_video),
      searchParams.get("offset") || 0,
      params.limit,
      params.nprobe,
      params.temporal_k,
      params.ocr_weight,
      params.asr_weight,
      params.max_interval,
      searchParams.get("selected") || undefined,
      params.target_features,
      params.auto_translate,
    );
    return {
      query: { q },
      params,
      selected: searchParams.get("selected") || undefined,
      offset: response.offset || 0,
      data: { total: getResultTotal(response), frames: response.frames || [] },
    };
  } catch (error) {
    return {
      query: { q },
      params,
      selected: searchParams.get("selected") || undefined,
      offset: searchParams.get("offset") || 0,
      data: { total: 0, frames: [] },
      error: error.message,
    };
  }
}

export default function Search() {
  const navigation = useNavigation();
  const submit = useSubmit();
  const { query = {}, params = {}, offset = 0, data = {}, selected, error } = useLoaderData();
  const playVideo = usePlayVideo();
  const {
    selected: selectedFrames,
    clearSelected,
    setActiveQuery,
    isShortlisted,
    isRejected,
    toggleShortlist,
    toggleReject,
    resetTriage,
  } = useSelected();
  const { q = "", id = null } = query;
  const { limit = limitOptions[0] } = params;
  const frames = data.frames || [];
  const candidates = groupTemporalCandidates(frames);
  const visibleCandidates = candidates.filter((candidate) => !isRejected(candidate.id));
  const total = getResultTotal(data) || candidates.length;
  const empty = visibleCandidates.length === 0;
  const queryKey = id ? `similar:${id}` : q.trim() || "all";
  const pageSize = parseInt(limit, 10) || 1;
  const [currentQuery, setCurrentQuery] = useState(q);
  const [density, setDensity] = useState(() => {
    const stored = Number(localStorage.getItem("vecna-grid-density"));
    return Number.isFinite(stored) && stored > 0 ? stored : 220;
  });
  const [history, setHistory] = useState(() => loadQueryHistory());

  useEffect(() => {
    setCurrentQuery(q);
    document.title = q || "Vecna Search";
  }, [q]);

  useEffect(() => {
    localStorage.setItem("vecna-grid-density", String(density));
  }, [density]);

  useEffect(() => {
    setActiveQuery(queryKey);
  }, [queryKey, setActiveQuery]);

  useEffect(() => {
    if (!id && q.trim()) {
      const nextHistory = rememberQuery(q, history);
      if (nextHistory.join("\u0000") !== history.join("\u0000")) {
        setHistory(nextHistory);
        saveQueryHistory(nextHistory);
      }
    }
  }, [history, id, q]);

  useEffect(() => {
    if (!currentQuery.trim() || currentQuery === q || id) return undefined;
    const timer = window.setTimeout(() => {
      submit({ ...params, q: currentQuery.trim(), offset: 0 }, { action: "/search" });
    }, 450);
    return () => window.clearTimeout(timer);
  }, [currentQuery, id, params, q, submit]);

  useEffect(() => {
    const handleKeyDown = (event) => {
      const action = getShortcutAction(event, {
        isInput: ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName),
      });
      if (action === "page-previous") {
        submit(serializeQueryState({ query: q, id, params, offset: Math.max(Number(offset) - pageSize, 0) }));
      }
      if (action === "page-next" && !empty) {
        submit(serializeQueryState({ query: q, id, params, offset: Number(offset) + pageSize }));
      }
      if (action === "focus-search" && !id) {
        event.preventDefault();
        document.querySelector("#search-bar")?.focus();
      }
      if (action === "focus-answer") {
        event.preventDefault();
        document.querySelector("#answer-form input[name=answer]")?.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [empty, id, offset, pageSize, params, q, submit, total]);

  const page = Math.floor(Number(offset) / pageSize) + 1;

  const goToFirstPage = () => submit(serializeQueryState({ query: q, id, params, offset: 0 }));
  const goToPreviousPage = () => submit(serializeQueryState({ query: q, id, params, offset: Math.max(Number(offset) - pageSize, 0) }));
  const goToNextPage = () => {
    if (!empty) submit(serializeQueryState({ query: q, id, params, offset: Number(offset) + pageSize }));
  };

  const handleOnSearch = (event = { preventDefault: () => {} }) => {
    event.preventDefault();
    if (currentQuery.trim()) submit({ ...params, q: currentQuery.trim(), offset: 0 }, { action: "/search" });
  };

  const handleOnSearchSimilar = (frame, keyframe) => {
    submit({ ...params, id: `${frame.video_id}#${keyframe}` }, { action: "/similar" });
  };

  const handleOnSearchNearby = (frame, keyframe) => {
    submit({ ...params, q: `[video:${frame.video_id}]`, selected: `${frame.video_id}#${keyframe}`, offset: 0 }, { action: "/search" });
  };

  const handleSubmitSelected = () => {
    if (selectedFrames.length === 0) {
      window.alert("Select at least one frame first.");
      return;
    }
    const [videoId] = selectedFrames[0].split("#");
    const frameIds = selectedFrames.map((frameId) => frameId.split("#")[1]);
    const blob = new Blob([`${videoId}, ${frameIds.join(", ")}`], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "query-result-kis.csv";
    link.click();
    URL.revokeObjectURL(link.href);
  };

  const handleResetQuery = () => {
    resetTriage(queryKey);
    if (id) {
      submit({ ...params, q: "", offset: 0 }, { action: "/search" });
      return;
    }
    setCurrentQuery("");
    submit({ ...params, offset: 0 }, { action: "/search" });
  };

  const handleClearHistory = () => {
    setHistory(clearQueryHistory());
  };

  const handleHistorySelect = (value) => {
    setCurrentQuery(value);
    submit({ ...params, q: value, offset: 0 }, { action: "/search" });
  };

  return (
    <div id="search-area" className="search-page">
      {!id && <Form id="search-form" onSubmit={handleOnSearch}>
        <div
          className="query-toolbar"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            const idFromDrop = event.dataTransfer.getData("application/x-vecna-frame");
            if (idFromDrop) submit({ ...params, id: idFromDrop }, { action: "/similar" });
          }}
        >
          <div className="query-toolbar-main">
            <img
              className={navigation.state === "loading" ? "query-spinner" : "query-spinner invisible"}
              src={SpinIcon}
              alt="Searching"
            />
            <textarea
              form="search-form"
              autoComplete="off"
              rows="1"
              className="query-input"
              name="q"
              id="search-bar"
              placeholder="Describe a scene, OCR text, or spoken phrase…"
              value={currentQuery}
              onChange={(event) => setCurrentQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && event.shiftKey) event.preventDefault();
              }}
            />
            <span className="query-status">{navigation.state === "loading" ? "Searching…" : "Auto-search"}</span>
          </div>
          <p className="query-helper">Type to search · use <code>ocr:</code> and <code>asr:</code> for evidence · drop a frame here for Similar</p>
        </div>
      </Form>}

      {id && (
        <div className="similar-source-banner">
          <div>
            <p className="eyebrow">Similar mode</p>
            <strong>Matches similar to {id}</strong>
          </div>
          <button type="button" className="toolbar-button" onClick={handleResetQuery}>Return to search</button>
        </div>
      )}

      {!id && (
        <div className="query-history-row">
          <details>
            <summary>Query history ({history.length})</summary>
            <div className="query-history-list">
              {history.length === 0 && <span className="helper-text">No saved queries yet.</span>}
              {history.map((item) => (
                <button key={item} type="button" onClick={() => handleHistorySelect(item)}>{item}</button>
              ))}
            </div>
          </details>
          <button type="button" className="toolbar-button" onClick={handleResetQuery}>Reset</button>
          <button type="button" className="toolbar-button" onClick={handleClearHistory} disabled={history.length === 0}>Clear history</button>
        </div>
      )}

      {!id && currentQuery.trim() && (
        <AdvanceQueryContainer
          q={currentQuery}
          onChange={setCurrentQuery}
          onSubmit={handleOnSearch}
        />
      )}

      <div id="nav-bar" className="results-toolbar">
        <div>
          <p className="eyebrow">Results</p>
          <h1>{q ? `Matches for “${q}”` : "Start with a query"}</h1>
          <span className="results-count">{total} candidates · page {page}</span>
        </div>
        <div className="results-toolbar-actions">
          <label className="density-control">Density <input type="range" min="160" max="360" step="10" value={density} onChange={(event) => setDensity(Number(event.target.value))} /> <output>{density}px</output></label>
          <button type="button" className="toolbar-button" onClick={goToFirstPage}>First</button>
          <button type="button" className="toolbar-button" onClick={goToPreviousPage}>Prev</button>
          <button type="button" className="toolbar-button" onClick={goToNextPage}>Next</button>
          <button type="button" className="toolbar-button toolbar-button-primary" onClick={handleSubmitSelected}>Export staged</button>
        </div>
      </div>

      {error && <div className="error-banner">Search unavailable: {error}</div>}
      {empty ? (
        <div className="empty-state">
          <strong>{q ? "No candidates yet" : "Search the indexed video collection"}</strong>
          <span>{q ? "Try a broader phrase or adjust a source preset." : "Results will appear here as you type."}</span>
        </div>
      ) : (
        <div className={navigation.state === "loading" ? "results-loading" : ""}>
          <FrameContainer density={density}>
            {visibleCandidates.map((candidate, index) => (
              <FrameItem
                key={`${candidate.id}-${index}`}
                id={candidate.id}
                video_id={candidate.video_id}
                frame_id={candidate.primaryKeyframe}
                keyframes={candidate.keyframes}
                thumbnail={`http://127.0.0.1:6900/api/files/${candidate.video_id}/${candidate.primaryKeyframe}`}
                timelineColor={getTimelineColor(index)}
                highlighted={selected === candidate.id}
                scores={candidate.scores}
                timelineScores={candidate.timelineScores}
                ocr={candidate.ocr}
                ocrBoxes={candidate.ocr_bboxes || candidate.ocr_boxes || candidate.bboxes}
                shortlisted={isShortlisted(candidate.id)}
                onPlay={(keyframe = candidate.primaryKeyframe) => playVideo(candidate, keyframe)}
                onSearchSimilar={(keyframe = candidate.primaryKeyframe) => handleOnSearchSimilar(candidate, keyframe)}
                onSearchNearby={(keyframe = candidate.primaryKeyframe) => handleOnSearchNearby(candidate, keyframe)}
                onToggleShortlist={() => toggleShortlist(candidate.id)}
                onToggleReject={() => toggleReject(candidate.id)}
              />
            ))}
          </FrameContainer>
        </div>
      )}
      <button type="button" className="sr-only" onClick={() => clearSelected()}>Clear staged frames</button>
    </div>
  );
}
