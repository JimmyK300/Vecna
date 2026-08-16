import React, { useState, useEffect } from "react";
import { useLoaderData, useSubmit, useNavigation, useOutletContext } from "react-router-dom";
import { search } from "../services/search.js";
import { AdvanceQueryContainer } from "../components/AdvanceQuery.jsx";
import { FrameItem, FrameContainer } from "../components/Frame.jsx";
import { usePlayVideo } from "../components/VideoPlayer.jsx";
import PreviousButton from "../assets/previous-btn.svg";
import NextButton from "../assets/next-btn.svg";
import HomeButton from "../assets/home-btn.svg";

export async function loader({ request }) {
  const url = new URL(request.url);
  const searchParams = url.searchParams;

  const q = searchParams.get("q") || "";
  const _offset = parseInt(searchParams.get("offset") || "0", 10);
  const limit = parseInt(searchParams.get("limit") || "20", 10);
  const nprobe = parseInt(searchParams.get("nprobe") || "32", 10);
  const temporal_k = parseInt(searchParams.get("temporal_k") || "2000", 10);
  const ocr_weight = parseFloat(searchParams.get("ocr_weight") || "0.5");
  const asr_weight = parseFloat(searchParams.get("asr_weight") || "0.0");
  const max_interval = parseInt(searchParams.get("max_interval") || "1000", 10);
  const auto_translate = searchParams.get("auto_translate") === "true";
  const en_to_vi_translate = searchParams.get("en_to_vi_translate") === "true";

  const target_features = searchParams.get("target_features") || "";
  const include_videos = searchParams.get("include_videos") || "";
  const exclude_videos = searchParams.get("exclude_videos") || "";

  if (!q && !include_videos && !exclude_videos) {
    return {
      query: { q: "" },
      params: { limit, nprobe, temporal_k, ocr_weight, asr_weight, max_interval, auto_translate, en_to_vi_translate, target_features, include_videos, exclude_videos },
      offset: 0,
      data: { total: 0, frames: [] },
    };
  }

  try {
    const res = await search(
      q,
      _offset,
      limit,
      nprobe,
      temporal_k,
      ocr_weight,
      asr_weight,
      max_interval,
      undefined,
      target_features,
      auto_translate,
      include_videos,
      exclude_videos,
      en_to_vi_translate
    );

    return {
      query: { q },
      params: { limit, nprobe, temporal_k, ocr_weight, asr_weight, max_interval, auto_translate, en_to_vi_translate, target_features, include_videos, exclude_videos },
      offset: res.offset || _offset,
      data: { total: res.total || 0, frames: res.frames || [] },
    };
  } catch (err) {
    console.error("Search failed:", err);
    return {
      query: { q },
      params: { limit, nprobe, temporal_k, ocr_weight, asr_weight, max_interval, auto_translate, en_to_vi_translate, target_features, include_videos, exclude_videos },
      offset: _offset,
      data: { total: 0, frames: [] },
      error: err.message,
    };
  }
}

export default function Search() {
  const { query, params, offset, data } = useLoaderData();
  const {
    selectedFeatures,
    ocrWeight: liveOcrWeight,
    asrWeight: liveAsrWeight,
    nprobe: liveNprobe,
    limit: liveLimit,
    temporalK: liveTemporalK,
    maxInterval: liveMaxInterval,
    autoTranslate: liveAutoTranslate,
    enToViTranslate: liveEnToViTranslate,
  } = useOutletContext();
  const submit = useSubmit();
  const navigation = useNavigation();
  const playVideo = usePlayVideo();

  const [searchQuery, setSearchQuery] = useState(query.q || "");
  const [autoTranslate, setAutoTranslate] = useState(params.auto_translate || false);
  const [enToViTranslate, setEnToViTranslate] = useState(params.en_to_vi_translate || false);
  const [includeVideos, setIncludeVideos] = useState(params.include_videos || "");
  const [excludeVideos, setExcludeVideos] = useState(params.exclude_videos || "");

  // VS Code Style Horizontal Resizable Splitter (Query Height)
  const [queryHeight, setQueryHeight] = useState(null);
  const [isResizingQuery, setIsResizingQuery] = useState(false);

  const isSearching = navigation.state === "loading";

  useEffect(() => {
    setSearchQuery(query.q || "");
    setAutoTranslate(params.auto_translate || false);
    setEnToViTranslate(params.en_to_vi_translate || false);
    setIncludeVideos(params.include_videos || "");
    setExcludeVideos(params.exclude_videos || "");
  }, [query.q, params]);

  const handleQueryMouseDown = (e) => {
    e.preventDefault();
    setIsResizingQuery(true);
  };

  useEffect(() => {
    const handleQueryMouseMove = (e) => {
      if (!isResizingQuery) return;
      const container = document.getElementById("query-section-wrapper");
      if (container) {
        const rect = container.getBoundingClientRect();
        const contentH = container.firstElementChild ? container.firstElementChild.offsetHeight : 210;
        const maxH = contentH + 4;
        const newH = Math.min(Math.max(70, e.clientY - rect.top), maxH);
        setQueryHeight(newH);
      }
    };

    const handleQueryMouseUp = () => {
      if (isResizingQuery) setIsResizingQuery(false);
    };

    if (isResizingQuery) {
      window.addEventListener("mousemove", handleQueryMouseMove);
      window.addEventListener("mouseup", handleQueryMouseUp);
    }
    return () => {
      window.removeEventListener("mousemove", handleQueryMouseMove);
      window.removeEventListener("mouseup", handleQueryMouseUp);
    };
  }, [isResizingQuery]);

  const triggerSearch = (
    newQ = searchQuery,
    newInc = includeVideos,
    newExc = excludeVideos
  ) => {
    setQueryHeight(null);
    const activeAutoTranslate = liveAutoTranslate !== undefined ? liveAutoTranslate : autoTranslate;
    const activeEnToViTranslate = liveEnToViTranslate !== undefined ? liveEnToViTranslate : enToViTranslate;
    const activeOcrWeight = liveOcrWeight !== undefined ? liveOcrWeight : (params.ocr_weight !== undefined ? params.ocr_weight : 0.5);
    const activeAsrWeight = liveAsrWeight !== undefined ? liveAsrWeight : (params.asr_weight !== undefined ? params.asr_weight : 0.0);
    const activeNprobe = liveNprobe ?? params.nprobe ?? 32;
    const activeLimit = liveLimit ?? params.limit ?? 20;
    const activeTemporalK = liveTemporalK ?? params.temporal_k ?? 2000;
    const activeMaxInterval = liveMaxInterval ?? params.max_interval ?? 1000;

    submit(
      {
        q: newQ,
        auto_translate: activeAutoTranslate ? "true" : "false",
        en_to_vi_translate: activeEnToViTranslate ? "true" : "false",
        include_videos: newInc,
        exclude_videos: newExc,
        target_features: (selectedFeatures || []).join(","),
        ocr_weight: activeOcrWeight,
        asr_weight: activeAsrWeight,
        nprobe: activeNprobe,
        limit: activeLimit,
        temporal_k: activeTemporalK,
        max_interval: activeMaxInterval,
        offset: 0,
      },
      { method: "get", action: "/search" }
    );
  };

  const handleAddIncludeVideo = (vid) => {
    if (!vid) return;
    const existing = includeVideos ? includeVideos.trim().split(/[,;\s]+/).filter(Boolean) : [];
    if (!existing.includes(vid)) {
      const nextInc = [...existing, vid].join(", ");
      setIncludeVideos(nextInc);
      triggerSearch(searchQuery, nextInc, excludeVideos);
    }
  };

  const handleAddExcludeVideo = (vid) => {
    if (!vid) return;
    const existing = excludeVideos ? excludeVideos.trim().split(/[,;\s]+/).filter(Boolean) : [];
    if (!existing.includes(vid)) {
      const nextExc = [...existing, vid].join(", ");
      setExcludeVideos(nextExc);
      triggerSearch(searchQuery, includeVideos, nextExc);
    }
  };

  const rawFrames = (data && data.frames) || [];
  const limit = parseInt(params.limit || "20", 10);

  // Client-side strict filtering for Exclude and Include video IDs
  let displayFrames = rawFrames;

  if (excludeVideos && excludeVideos.trim().length > 0) {
    const excludes = excludeVideos
      .split(/[,;\s]+/)
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);
    if (excludes.length > 0) {
      displayFrames = displayFrames.filter((frame) => {
        const vId = String(frame.video_id || "").toLowerCase();
        return !excludes.some((ex) => vId.includes(ex));
      });
    }
  }

  if (includeVideos && includeVideos.trim().length > 0) {
    const includes = includeVideos
      .split(/[,;\s]+/)
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);
    if (includes.length > 0) {
      displayFrames = displayFrames.filter((frame) => {
        const vId = String(frame.video_id || "").toLowerCase();
        return includes.some((inc) => vId.includes(inc));
      });
    }
  }

  const totalCount = data.total || displayFrames.length;
  const hasNextPage = rawFrames.length >= limit && (offset + limit < (data.total || Infinity));

  // Global & Search Navigation Keyboard Shortcuts
  useEffect(() => {
    const handleGlobalKeyDown = (e) => {
      const activeEl = document.activeElement;
      const isInInput = activeEl && ["INPUT", "TEXTAREA", "SELECT"].includes(activeEl.tagName);

      // 1. Shift + Enter: Submit Answer from anywhere
      if (e.shiftKey && e.key === "Enter") {
        const submitBtn = document.getElementById("submit-selected-btn");
        if (submitBtn) {
          e.preventDefault();
          submitBtn.click();
          return;
        }
      }

      // 2. '/' key: Focus Search Bar (when not in input)
      if (e.key === "/" && !isInInput) {
        e.preventDefault();
        const mainInput = document.querySelector('[data-query-input="main"]');
        if (mainInput) {
          mainInput.scrollIntoView({ behavior: "smooth", block: "center" });
          mainInput.focus();
        }
        return;
      }

      // 3. Shift + ? (Shift + /): Jump to Answer Section
      if (e.shiftKey && (e.key === "?" || e.key === "/")) {
        e.preventDefault();
        const answerSection = document.getElementById("answer-sidebar-container");
        if (answerSection) {
          answerSection.scrollIntoView({ behavior: "smooth", block: "center" });
        }
        return;
      }

      // 4. Tab / Shift + Tab: Cycle input fields
      if (e.key === "Tab" && isInInput) {
        const inputs = Array.from(
          document.querySelectorAll('[data-query-input="main"], [data-query-input="ocr"], [data-query-input="speech"]')
        );
        if (inputs.length > 0) {
          const currentIdx = inputs.indexOf(activeEl);
          if (currentIdx !== -1) {
            e.preventDefault();
            const nextIdx = e.shiftKey
              ? (currentIdx - 1 + inputs.length) % inputs.length
              : (currentIdx + 1) % inputs.length;
            inputs[nextIdx].focus();
            return;
          }
        }
      }

      // If user is currently typing inside an input, do not intercept navigation hotkeys below
      if (isInInput) return;

      // 5. Up Arrow (↑): Previous Page
      if (e.key === "ArrowUp") {
        if (offset > 0) {
          e.preventDefault();
          goToPreviousPage();
        }
        return;
      }

      // 6. Down Arrow (↓): Next Page
      if (e.key === "ArrowDown") {
        if (hasNextPage) {
          e.preventDefault();
          goToNextPage();
        }
        return;
      }

      // 7. Shift + 1 .. Shift + 9 & Shift + 0: Play Result 1-10
      if (e.shiftKey && e.code && e.code.startsWith("Digit")) {
        const digit = parseInt(e.code.replace("Digit", ""), 10);
        const targetIdx = digit === 0 ? 9 : digit - 1;
        if (targetIdx < displayFrames.length) {
          e.preventDefault();
          const targetFrame = displayFrames[targetIdx];
          const kf = targetFrame.time_line ? targetFrame.time_line[0] : targetFrame.frame_id;
          playVideo({ video_id: targetFrame.video_id, frame_id: kf }, kf);
        }
        return;
      }
    };

    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, [offset, hasNextPage, displayFrames, limit, params, query, submit, playVideo]);

  const goToFirstPage = () => {
    if (offset > 0) {
      submit({ ...query, ...params, offset: 0 }, { action: "/search" });
    }
  };

  const goToPreviousPage = () => {
    if (offset > 0) {
      submit(
        {
          ...query,
          ...params,
          offset: Math.max(parseInt(offset) - limit, 0),
        },
        { action: "/search" }
      );
    }
  };

  const goToNextPage = () => {
    if (hasNextPage) {
      submit(
        {
          ...query,
          ...params,
          offset: parseInt(offset) + limit,
        },
        { action: "/search" }
      );
    }
  };

  const renderNavBar = (keySuffix = "top") => (
    <div
      key={keySuffix}
      id={`nav-bar-${keySuffix}`}
      className="px-2.5 py-1.5 flex flex-row justify-between items-center text-sm font-bold bg-white border border-gray-200 rounded-xl shrink-0 shadow-sm"
    >
      <div className="flex items-center gap-2 text-xs text-gray-700 font-mono">
        <span>Total: <strong className="text-blue-700">{totalCount}</strong></span>
        <span className="text-gray-300">|</span>
        <span>Showing: <strong className="text-emerald-700">{displayFrames.length}</strong></span>
      </div>

      <div className="flex flex-row items-center gap-1.5">
        {/* Home Button */}
        <button
          onClick={goToFirstPage}
          disabled={offset === 0}
          className={`p-1.5 rounded-lg border flex items-center justify-center transition-all ${
            offset > 0
              ? "bg-white hover:bg-blue-600 hover:text-white border-gray-300 text-gray-700 shadow-sm hover:scale-105 active:scale-95 cursor-pointer"
              : "bg-gray-100 text-gray-300 border-gray-200 cursor-not-allowed"
          }`}
          title="First Page"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l9-9 9 9M5 10v10a1 1 0 001 1h3a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1h3a1 1 0 001-1V10" />
          </svg>
        </button>

        {/* Previous Button */}
        <button
          onClick={goToPreviousPage}
          disabled={offset === 0}
          className={`p-1.5 rounded-lg border flex items-center justify-center transition-all ${
            offset > 0
              ? "bg-white hover:bg-blue-600 hover:text-white border-gray-300 text-gray-700 shadow-sm hover:scale-105 active:scale-95 cursor-pointer"
              : "bg-gray-100 text-gray-300 border-gray-200 cursor-not-allowed"
          }`}
          title="Previous Page"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>

        {/* Page Badge */}
        <div className="px-3 py-1 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg text-xs font-bold text-blue-900 shadow-inner font-mono flex items-center gap-1">
          <span className="text-gray-500 font-normal">Page</span>
          <span className="text-blue-700 font-extrabold text-sm">{Math.floor(offset / limit) + 1}</span>
        </div>

        {/* Next Button */}
        <button
          onClick={goToNextPage}
          disabled={!hasNextPage}
          className={`p-1.5 rounded-lg border flex items-center justify-center transition-all ${
            hasNextPage
              ? "bg-white hover:bg-blue-600 hover:text-white border-gray-300 text-gray-700 shadow-sm hover:scale-105 active:scale-95 cursor-pointer"
              : "bg-gray-100 text-gray-300 border-gray-200 cursor-not-allowed"
          }`}
          title="Next Page"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>
    </div>
  );

  const handleSearchSimilar = (frameKey) => {
    submit(
      {
        id: frameKey,
        target_features: (selectedFeatures || []).join(","),
        ocr_weight: params.ocr_weight !== undefined ? params.ocr_weight : 0.5,
        asr_weight: params.asr_weight !== undefined ? params.asr_weight : 0.0,
        nprobe: params.nprobe ?? 32,
        limit: params.limit ?? 20,
        temporal_k: params.temporal_k ?? 2000,
        max_interval: params.max_interval ?? 1000,
      },
      { action: "/similar" }
    );
  };

  return (
    <div
      id="search-area"
      className={`flex flex-col w-full h-full min-h-0 overflow-hidden ${
        isResizingQuery ? "cursor-row-resize select-none" : ""
      }`}
    >
      {/* Panel 2: Center Top Query Box (Resizable Height) */}
      <div
        id="query-section-wrapper"
        style={queryHeight ? { height: `${queryHeight}px` } : {}}
        className="w-full flex flex-col shrink-0 overflow-y-auto"
      >
        <AdvanceQueryContainer
          q={searchQuery}
          onChange={(newQ) => {
            setSearchQuery(newQ);
            triggerSearch(newQ, includeVideos, excludeVideos);
          }}
          autoTranslate={autoTranslate}
          onToggleAutoTranslate={(val) => {
            setAutoTranslate(val);
            triggerSearch(searchQuery, includeVideos, excludeVideos);
          }}
          includeVideos={includeVideos}
          onIncludeVideosChange={(val) => {
            setIncludeVideos(val);
            if (val) setExcludeVideos("");
            triggerSearch(searchQuery, val, val ? "" : excludeVideos);
          }}
          excludeVideos={excludeVideos}
          onExcludeVideosChange={(val) => {
            setExcludeVideos(val);
            if (val) setIncludeVideos("");
            triggerSearch(searchQuery, val ? "" : includeVideos, val);
          }}
          onApplyVideoFilters={(newInc, newExc) => {
            setIncludeVideos(newInc);
            setExcludeVideos(newExc);
            triggerSearch(searchQuery, newInc, newExc);
          }}
          isSearching={isSearching}
        />
      </div>

      {/* VS Code Style Horizontal Resizable Splitter Bar */}
      <div
        onMouseDown={handleQueryMouseDown}
        className={`h-1.5 hover:h-1.5 w-full bg-gray-300 hover:bg-blue-500 cursor-row-resize select-none flex items-center justify-center transition-colors shrink-0 my-1 z-20 ${
          isResizingQuery ? "bg-blue-600" : ""
        }`}
        title="Drag up / down to resize Query Box"
      />

      {/* Panel 3: Center Bottom Results Grid (Scrollable Container) */}
      <div className="flex-1 flex flex-col gap-2 min-h-0 overflow-y-auto pr-1">
        {/* Top Navigation Bar */}
        {renderNavBar("top")}

        {/* Frame Results Grid */}
        {displayFrames.length === 0 ? (
          <div className="w-full text-center p-8 bg-white border border-gray-300 rounded text-gray-500 text-sm font-medium">
            {isSearching ? "Searching keyframes..." : "No keyframes found. Check your search query or video filter parameters."}
          </div>
        ) : (
          <div className={isSearching ? "animate-pulse" : ""}>
            <FrameContainer id="result">
              {displayFrames.map((frame, idx) => {
                const keyframesList = frame.time_line || [frame.frame_id];
                const scoresList = frame.time_line_scores || [];
                const isTemporalSeq = keyframesList.length > 1;

                return keyframesList.map((kf, kfIdx) => {
                  const sc = (scoresList && scoresList[kfIdx]) || frame.scores;
                  const frameKey = `${frame.video_id}#${kf}`;
                  return (
                    <FrameItem
                      key={`${frameKey}-${idx}-${kfIdx}`}
                      id={frameKey}
                      video_id={frame.video_id}
                      frame_id={kf}
                      thumbnail={`http://127.0.0.1:6900/api/files/${frame.video_id}/${kf}`}
                      scores={sc}
                      ocr={frame.ocr}
                      temporalStep={isTemporalSeq ? `${kfIdx + 1}/${keyframesList.length}` : null}
                      onPlay={() => playVideo({ video_id: frame.video_id, frame_id: kf }, kf)}
                      onSearchSimilar={() => handleSearchSimilar(frameKey)}
                      onAddIncludeVideo={handleAddIncludeVideo}
                      onAddExcludeVideo={handleAddExcludeVideo}
                    />
                  );
                });
              })}
            </FrameContainer>
          </div>
        )}

        {/* Bottom Navigation Bar (Dễ dàng chuyển trang ở cuối danh sách mà không cần cuộn ngược lên) */}
        {displayFrames.length > 0 && renderNavBar("bottom")}
      </div>
    </div>
  );
}
