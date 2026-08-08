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
  limitOptions,
  nprobeOption,
  temporal_k_default,
  ocr_weight_default,
  asr_weight_default,
  max_interval_default,
} from "../resources/options.js";

function appendVideoFilters(query, includeVideo, excludeVideo) {
  const include = includeVideo
    ? `[video:${includeVideo.split(",").map((item) => item.trim()).filter(Boolean).join(",")}]`
    : "";
  const exclude = excludeVideo
    ? `[-video:${excludeVideo.split(",").map((item) => item.trim()).filter(Boolean).join(",")}]`
    : "";
  return [query, include, exclude].filter(Boolean).join(" ").trim();
}

export async function loader({ request }) {
  const url = new URL(request.url);
  const searchParams = url.searchParams;
  const q = searchParams.get("q") || "";
  const include_video = searchParams.get("include_video") || "";
  const exclude_video = searchParams.get("exclude_video") || "";

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
    exclude_video,
  };

  if (!q) {
    return { query: {}, params, selected: undefined, offset: 0, data: { total: 0, frames: [] } };
  }

  try {
    const response = await search(
      appendVideoFilters(q.replace(/[|\\]/g, ";"), include_video, exclude_video),
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
      data: { total: response.total || 0, frames: response.frames || [] },
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

function frameEntries(frame) {
  const timeLines = frame.time_line?.length
    ? frame.time_line
    : [frame.frame_id || String(frame.id || "").split("#")[1]].filter(Boolean);
  return timeLines.map((keyframe, index) => ({
    frame,
    keyframe,
    scores: frame.time_line_scores?.[index] || frame.scores,
  }));
}

export default function Search() {
  const navigation = useNavigation();
  const submit = useSubmit();
  const { query = {}, params = {}, offset = 0, data = {}, selected, error } = useLoaderData();
  const playVideo = usePlayVideo();
  const { selected: selectedFrames, clearSelected } = useSelected();
  const { q = "", id = null } = query;
  const { limit = limitOptions[0] } = params;
  const frames = data.frames || [];
  const total = data.total || 0;
  const [currentQuery, setCurrentQuery] = useState(q);
  const [density, setDensity] = useState(() => localStorage.getItem("vecna-grid-density") || "compact");

  useEffect(() => {
    setCurrentQuery(q);
    document.title = q || "Vecna Search";
  }, [q]);

  useEffect(() => {
    localStorage.setItem("vecna-grid-density", density);
  }, [density]);

  useEffect(() => {
    if (!currentQuery.trim() || currentQuery === q || id) return undefined;
    const timer = window.setTimeout(() => {
      submit({ ...params, q: currentQuery.trim(), offset: 0 }, { action: "/search" });
    }, 450);
    return () => window.clearTimeout(timer);
  }, [currentQuery, id, params, q, submit]);

  useEffect(() => {
    const handleKeyDown = (event) => {
      const isInput = ["INPUT", "TEXTAREA"].includes(event.target.tagName);
      if (isInput) return;
      if (event.key === "ArrowUp") goToPreviousPage();
      if (event.key === "ArrowDown") goToNextPage();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  });

  const pageSize = parseInt(limit, 10) || 1;
  const page = Math.floor(Number(offset) / pageSize) + 1;
  const empty = frames.length === 0;

  const goToFirstPage = () => submit({ ...query, ...params, offset: 0 });
  const goToPreviousPage = () => submit({ ...query, ...params, offset: Math.max(Number(offset) - pageSize, 0) });
  const goToNextPage = () => {
    if (!empty) submit({ ...query, ...params, offset: Number(offset) + pageSize });
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

  return (
    <div id="search-area" className="search-page">
      <Form id="search-form" onSubmit={handleOnSearch}>
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
          <p className="query-helper">Type to search · use <code>ocr:</code> and <code>asr:</code> for evidence · drop a frame here for similar search</p>
        </div>
      </Form>

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
          <div className="density-toggle" role="group" aria-label="Result density">
            <button type="button" className={density === "compact" ? "active" : ""} onClick={() => setDensity("compact")}>Compact</button>
            <button type="button" className={density === "detailed" ? "active" : ""} onClick={() => setDensity("detailed")}>Detailed</button>
          </div>
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
            {frames.flatMap(frameEntries).map(({ frame, keyframe, scores }, index) => (
              <FrameItem
                key={`${frame.id || frame.video_id}-${keyframe}-${index}`}
                id={`${frame.video_id}#${keyframe}`}
                video_id={frame.video_id}
                frame_id={keyframe}
                thumbnail={`http://127.0.0.1:6900/api/files/${frame.video_id}/${keyframe}`}
                timelineColor={getTimelineColor(index)}
                highlighted={selected === `${frame.video_id}#${keyframe}`}
                scores={scores}
                ocr={frame.ocr}
                onPlay={() => playVideo(frame, keyframe)}
                onSearchSimilar={() => handleOnSearchSimilar(frame, keyframe)}
                onSearchNearby={() => handleOnSearchNearby(frame, keyframe)}
              />
            ))}
          </FrameContainer>
        </div>
      )}
      <button type="button" className="sr-only" onClick={() => clearSelected()}>Clear staged frames</button>
    </div>
  );
}
