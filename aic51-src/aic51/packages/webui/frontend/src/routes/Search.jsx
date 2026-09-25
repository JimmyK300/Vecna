import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useLoaderData, useSubmit, useNavigation, useOutletContext } from "react-router-dom";
import { search, cancelCurrentSearch } from "../services/search.js";
import { AdvanceQueryContainer } from "../components/AdvanceQuery.jsx";
import { FrameItem, FrameContainer } from "../components/Frame.jsx";
import { usePlayVideo } from "../components/VideoPlayer.jsx";
import PreviousButton from "../assets/previous-btn.svg";
import NextButton from "../assets/next-btn.svg";
import HomeButton from "../assets/home-btn.svg";

// Component that intercepts mouse wheel and scrolls exclusively horizontally without moving parent page vertically
function HorizontalWheelScroll({ children, className }) {
  const scrollRef = useRef(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const handleWheel = (e) => {
      if (el.scrollWidth > el.clientWidth) {
        e.preventDefault();
        e.stopPropagation();
        el.scrollLeft += (e.deltaY !== 0 ? e.deltaY : e.deltaX) * 1.5;
      }
    };

    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => {
      el.removeEventListener("wheel", handleWheel);
    };
  }, []);

  return (
    <div ref={scrollRef} className={className}>
      {children}
    </div>
  );
}

const CHUNK_SIZE = 300;

export async function loader({ request }) {
  const url = new URL(request.url);
  const searchParams = url.searchParams;

  const q = searchParams.get("q") || "";
  const requestedOffset = parseInt(searchParams.get("offset") || "0", 10);
  const limit = parseInt(searchParams.get("limit") || "20", 10);
  const nprobe = parseInt(searchParams.get("nprobe") || "32", 10);
  const temporal_k = parseInt(searchParams.get("temporal_k") || "200", 10);
  const ocr_weight = parseFloat(searchParams.get("ocr_weight") || "0.0");
  const asr_weight = parseFloat(searchParams.get("asr_weight") || "0.0");
  const ocr_alpha = parseFloat(searchParams.get("ocr_alpha") || "0.0");
  const asr_alpha = parseFloat(searchParams.get("asr_alpha") || "0.0");
  const max_interval = parseInt(searchParams.get("max_interval") || "1000", 10);
  const auto_translate = searchParams.get("auto_translate") === "true";
  const en_to_vi_translate = searchParams.get("en_to_vi_translate") === "true";

  const target_features = searchParams.get("target_features") || "";
  const include_videos = searchParams.get("include_videos") || "";
  const exclude_videos = searchParams.get("exclude_videos") || "";
  const collection = searchParams.get("collection") || "";

  const chunkStart = Math.floor(requestedOffset / CHUNK_SIZE) * CHUNK_SIZE;
  const initialLocalOffset = Math.floor((requestedOffset - chunkStart) / limit) * limit;

  if (!q && !include_videos && !exclude_videos) {
    return {
      query: { q: "" },
      params: { limit, nprobe, temporal_k, ocr_weight, asr_weight, ocr_alpha, asr_alpha, max_interval, auto_translate, en_to_vi_translate, target_features, include_videos, exclude_videos, collection },
      offset: requestedOffset,
      chunkStart: 0,
      initialLocalOffset: 0,
      data: { total: 0, frames: [] },
    };
  }

  try {
    const res = await search(
      q,
      chunkStart,
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
      en_to_vi_translate,
      ocr_alpha,
      asr_alpha,
      collection,
    );

    if (res && res.canceled) {
      return {
        query: { q },
        params: { limit, nprobe, temporal_k, ocr_weight, asr_weight, ocr_alpha, asr_alpha, max_interval, auto_translate, en_to_vi_translate, target_features, include_videos, exclude_videos, collection },
        offset: requestedOffset,
        chunkStart,
        initialLocalOffset: 0,
        data: { total: 0, frames: [] },
      };
    }

    return {
      query: { q },
      params: { limit, nprobe, temporal_k, ocr_weight, asr_weight, ocr_alpha, asr_alpha, max_interval, auto_translate, en_to_vi_translate, target_features, include_videos, exclude_videos, collection },
      offset: requestedOffset,
      chunkStart: res.offset !== undefined ? res.offset : chunkStart,
      initialLocalOffset,
      data: { total: res.total || 0, frames: res.frames || [], translation_failed: !!res.translation_failed },
    };
  } catch (err) {
    console.error("Search failed:", err);
    return {
      query: { q },
      params: { limit, nprobe, temporal_k, ocr_weight, asr_weight, ocr_alpha, asr_alpha, max_interval, auto_translate, en_to_vi_translate, target_features, include_videos, exclude_videos, collection },
      offset: requestedOffset,
      chunkStart,
      initialLocalOffset: 0,
      data: { total: 0, frames: [] },
      error: err.message,
    };
  }
}

export default function Search() {
  const { query, params, offset, chunkStart = 0, initialLocalOffset = 0, data } = useLoaderData();
  const {
    selectedFeatures,
    ocrWeight: liveOcrWeight,
    asrWeight: liveAsrWeight,
    ocrAlpha: liveOcrAlpha,
    asrAlpha: liveAsrAlpha,
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
  const [collection, setCollection] = useState(() => {
    let col = params.collection || localStorage.getItem("aic51_collection") || "workspace";
    if (col === "testcol1") col = "workspace";
    if (col === "testcol2") col = "workspace2";
    return col;
  });
  const [autoTranslate, setAutoTranslate] = useState(params.auto_translate || false);
  const [enToViTranslate, setEnToViTranslate] = useState(params.en_to_vi_translate || false);
  const [includeVideos, setIncludeVideos] = useState(params.include_videos || "");
  const [excludeVideos, setExcludeVideos] = useState(params.exclude_videos || "");
  const [appliedInclude, setAppliedInclude] = useState(params.include_videos || "");
  const [appliedExclude, setAppliedExclude] = useState(params.exclude_videos || "");

  // VS Code Style Horizontal Resizable Splitter (Query Height)
  const [queryHeight, setQueryHeight] = useState(null);
  const [isResizingQuery, setIsResizingQuery] = useState(false);

  const handleResetQueryHeight = useCallback(() => {
    setQueryHeight(null);
  }, []);

  const handleCancelSearch = useCallback(() => {
    cancelCurrentSearch();
    try {
      window.stop();
    } catch (e) {}
  }, []);

  const isSearching = navigation.state === "loading";

  useEffect(() => {
    setSearchQuery(query.q || "");
    setAutoTranslate(params.auto_translate || false);
    setEnToViTranslate(params.en_to_vi_translate || false);
    setIncludeVideos(params.include_videos || "");
    setExcludeVideos(params.exclude_videos || "");
    setAppliedInclude(params.include_videos || "");
    setAppliedExclude(params.exclude_videos || "");
    if (params.collection) {
      setCollection(params.collection);
      localStorage.setItem("aic51_collection", params.collection);
    }
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
        const blueBox = container.firstElementChild;
        const maxAllowed = blueBox ? blueBox.offsetHeight + 8 : window.innerHeight - 80;
        const newH = Math.min(Math.max(45, e.clientY - rect.top), maxAllowed);
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
    newExc = excludeVideos,
    newCol = collection
  ) => {
    const activeAutoTranslate = liveAutoTranslate !== undefined ? liveAutoTranslate : autoTranslate;
    const activeEnToViTranslate = liveEnToViTranslate !== undefined ? liveEnToViTranslate : enToViTranslate;
    const activeOcrWeight = liveOcrWeight !== undefined ? liveOcrWeight : (params.ocr_weight !== undefined ? params.ocr_weight : 0.0);
    const activeAsrWeight = liveAsrWeight !== undefined ? liveAsrWeight : (params.asr_weight !== undefined ? params.asr_weight : 0.0);
    const activeOcrAlpha = liveOcrAlpha !== undefined ? liveOcrAlpha : (params.ocr_alpha !== undefined ? params.ocr_alpha : 0.0);
    const activeAsrAlpha = liveAsrAlpha !== undefined ? liveAsrAlpha : (params.asr_alpha !== undefined ? params.asr_alpha : 0.0);
    const activeNprobe = liveNprobe ?? params.nprobe ?? 32;
    const activeLimit = liveLimit ?? params.limit ?? 20;
    const activeTemporalK = liveTemporalK ?? params.temporal_k ?? 200;
    const activeMaxInterval = liveMaxInterval ?? params.max_interval ?? 1000;

    submit(
      {
        q: newQ,
        collection: newCol,
        auto_translate: activeAutoTranslate ? "true" : "false",
        en_to_vi_translate: activeEnToViTranslate ? "true" : "false",
        include_videos: newInc,
        exclude_videos: newExc,
        target_features: (selectedFeatures || []).join(","),
        ocr_weight: activeOcrWeight,
        asr_weight: activeAsrWeight,
        ocr_alpha: activeOcrAlpha,
        asr_alpha: activeAsrAlpha,
        nprobe: activeNprobe,
        limit: activeLimit,
        temporal_k: activeTemporalK,
        max_interval: activeMaxInterval,
        offset: 0,
      },
      { method: "get", action: "/search" }
    );
  };

  const handleCollectionChange = (newCol) => {
    setCollection(newCol);
    localStorage.setItem("aic51_collection", newCol);
    triggerSearch(searchQuery, includeVideos, excludeVideos, newCol);
  };

  const handleAddIncludeVideo = (vid) => {
    if (!vid) return;
    const existing = includeVideos ? includeVideos.trim().split(/[,;\s]+/).filter(Boolean) : [];
    if (!existing.includes(vid)) {
      const nextInc = [...existing, vid].join(", ");
      setIncludeVideos(nextInc);
    }
  };

  const handleAddExcludeVideo = (vid) => {
    if (!vid) return;
    const existing = excludeVideos ? excludeVideos.trim().split(/[,;\s]+/).filter(Boolean) : [];
    if (!existing.includes(vid)) {
      const nextExc = [...existing, vid].join(", ");
      setExcludeVideos(nextExc);
    }
  };

  const rawFrames = (data && data.frames) || [];
  const limit = parseInt(params.limit || "20", 10);

  // Local offset for instant client-side pagination within candidate pool (0ms latency)
  const [localOffset, setLocalOffset] = useState(initialLocalOffset);

  useEffect(() => {
    setLocalOffset(initialLocalOffset);
  }, [data, initialLocalOffset]);

  // Client-side reactive candidate pool filtering using applied filters (Option A: Instant Replenishment)
  const filteredPool = useMemo(() => {
    let pool = rawFrames;
    const currentExc = (appliedExclude || "").trim().toLowerCase();
    const currentInc = (appliedInclude || "").trim().toLowerCase();

    if (currentExc) {
      const excludes = currentExc.split(/[,;\s]+/).map((s) => s.trim()).filter(Boolean);
      if (excludes.length > 0) {
        pool = pool.filter((frame) => {
          const vId = String(frame.video_id || "").toLowerCase();
          const fId = String(frame.frame_id || "").toLowerCase();
          const isDirectExcluded = excludes.some((ex) => vId.startsWith(ex) || fId.startsWith(ex) || vId.includes(ex));
          if (isDirectExcluded) return false;
          if (Array.isArray(frame.time_line) && frame.time_line.length > 1) {
            return !frame.time_line.some((step) => {
              const s = String(step).toLowerCase();
              return excludes.some((ex) => s.startsWith(ex) || s.includes(ex));
            });
          }
          return true;
        });
      }
    }

    if (currentInc) {
      const includes = currentInc.split(/[,;\s]+/).map((s) => s.trim()).filter(Boolean);
      if (includes.length > 0) {
        pool = pool.filter((frame) => {
          const vId = String(frame.video_id || "").toLowerCase();
          const fId = String(frame.frame_id || "").toLowerCase();
          return includes.some((inc) => vId.startsWith(inc) || fId.startsWith(inc) || vId.includes(inc));
        });
      }
    }

    return pool;
  }, [rawFrames, appliedExclude, appliedInclude]);

  // Ensure safeOffset stays within bounds after dynamic filtering
  const maxLocalOffset = Math.max(0, Math.floor(Math.max(0, filteredPool.length - 1) / limit) * limit);
  const safeOffset = Math.min(localOffset, maxLocalOffset);

  const displayFrames = filteredPool.slice(safeOffset, safeOffset + limit);
  const totalCount = filteredPool.length > 0 ? (data.total || filteredPool.length) : 0;
  const globalItemIndex = (chunkStart || 0) + safeOffset;
  const currentPage = Math.floor(globalItemIndex / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(totalCount / limit));

  const hasPrevPage = globalItemIndex > 0;
  const hasNextPage = (safeOffset + limit < filteredPool.length) || (globalItemIndex + limit < totalCount);

  // Temporal Grouping by Video ID (Row Reel | Stack Cards | Flat Grid)
  const [viewMode, setViewMode] = useState("row"); // "row" | "grouped" | "flat"

  const isTemporalResult = useMemo(() => {
    return displayFrames.some((frame) => (frame.time_line || []).length > 1);
  }, [displayFrames]);

  const groupedVideos = useMemo(() => {
    if (!isTemporalResult) return [];

    const groupsMap = new Map();

    for (const frame of displayFrames) {
      const vId = frame.video_id;
      if (!groupsMap.has(vId)) {
        groupsMap.set(vId, {
          video_id: vId,
          fps: frame.fps || 25,
          maxScore: frame.scores?.final ?? 0,
          sequences: [],
        });
      }
      const group = groupsMap.get(vId);
      const score = frame.scores?.final ?? 0;
      if (score > group.maxScore) {
        group.maxScore = score;
      }
      group.sequences.push(frame);
    }

    // Sort sequences inside each video group descending by score
    for (const group of groupsMap.values()) {
      group.sequences.sort((a, b) => (b.scores?.final ?? 0) - (a.scores?.final ?? 0));
    }

    // Sort video groups descending by their highest sequence score
    const sortedGroups = Array.from(groupsMap.values()).sort(
      (a, b) => b.maxScore - a.maxScore
    );

    return sortedGroups;
  }, [displayFrames, isTemporalResult]);

  // Per-video expanded sequence counts (default: 1 sequence per video)
  const [expandedCounts, setExpandedCounts] = useState({});

  const handleShowMoreSeq = (vId, totalSeqs) => {
    setExpandedCounts((prev) => {
      const current = prev[vId] ?? 1;
      return { ...prev, [vId]: Math.min(current + 1, totalSeqs) };
    });
  };

  const handleCollapseSeq = (vId) => {
    setExpandedCounts((prev) => ({ ...prev, [vId]: 1 }));
  };

  const handleShowAllSeq = (vId, totalSeqs) => {
    setExpandedCounts((prev) => ({ ...prev, [vId]: totalSeqs }));
  };

  const handleExpandAllVideos = () => {
    const allExpanded = {};
    for (const g of groupedVideos) {
      allExpanded[g.video_id] = g.sequences.length;
    }
    setExpandedCounts(allExpanded);
  };

  const handleCollapseAllVideos = () => {
    setExpandedCounts({});
  };

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
        if (hasPrevPage) {
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
  }, [safeOffset, hasPrevPage, hasNextPage, displayFrames, limit, params, query, submit, playVideo, localOffset, filteredPool.length, chunkStart, globalItemIndex]);

  const goToFirstPage = () => {
    if (chunkStart === 0 && safeOffset > 0) {
      setLocalOffset(0);
    } else if (globalItemIndex > 0) {
      submit({ ...query, ...params, collection, include_videos: includeVideos, exclude_videos: excludeVideos, offset: 0 }, { action: "/search" });
    }
  };

  const goToPreviousPage = () => {
    if (safeOffset >= limit) {
      setLocalOffset(safeOffset - limit);
    } else if (globalItemIndex > 0) {
      const prevGlobalOffset = Math.max(0, globalItemIndex - limit);
      submit(
        {
          ...query,
          ...params,
          collection,
          include_videos: includeVideos,
          exclude_videos: excludeVideos,
          offset: prevGlobalOffset,
        },
        { action: "/search" }
      );
    }
  };

  const goToNextPage = () => {
    if (safeOffset + limit < filteredPool.length) {
      setLocalOffset(safeOffset + limit);
    } else if (hasNextPage) {
      const nextGlobalOffset = globalItemIndex + limit;
      submit(
        {
          ...query,
          ...params,
          collection,
          include_videos: includeVideos,
          exclude_videos: excludeVideos,
          offset: nextGlobalOffset,
        },
        { action: "/search" }
      );
    }
  };

  const renderNavBar = (keySuffix = "top") => (
    <div
      key={keySuffix}
      id={`nav-bar-${keySuffix}`}
      className="px-2.5 py-1.5 flex flex-row justify-between items-center text-sm font-bold bg-white border border-gray-200 rounded-xl shrink-0 shadow-sm flex-wrap gap-2"
    >
      <div className="flex items-center gap-2 text-xs text-gray-700 font-mono flex-wrap">
        <span>Total: <strong className="text-blue-700">{totalCount}</strong></span>
        <span className="text-gray-300">|</span>
        <span>Showing: <strong className="text-emerald-700">{displayFrames.length}</strong></span>
        {isTemporalResult && (
          <>
            <span className="text-gray-300">|</span>
            <span>Videos: <strong className="text-sky-700 font-bold">{groupedVideos.length}</strong></span>
          </>
        )}
      </div>

      <div className="flex flex-row items-center gap-1.5 flex-wrap">
        {/* Toggle between Single Row Reel, Group Stack, and Flat View Mode (Only for Temporal Search) */}
        {isTemporalResult && (
          <div className="flex items-center gap-1.5 mr-1 flex-wrap">
            {viewMode === "grouped" && (
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={handleExpandAllVideos}
                  className="text-[10px] font-bold px-2 py-1 rounded-lg bg-sky-50 hover:bg-sky-100 text-sky-800 border border-sky-300 shadow-2xs transition-colors cursor-pointer"
                  title="Show all sequences for all videos"
                >
                  Show All
                </button>
                <button
                  type="button"
                  onClick={handleCollapseAllVideos}
                  className="text-[10px] font-semibold px-2 py-1 rounded-lg bg-gray-50 hover:bg-gray-100 text-gray-700 border border-gray-300 shadow-2xs transition-colors cursor-pointer"
                  title="Collapse all videos to 1 default sequence"
                >
                  Collapse All
                </button>
              </div>
            )}

            <div className="flex items-center bg-gray-100 p-0.5 rounded-lg border border-gray-200 shadow-2xs">
              <button
                type="button"
                onClick={() => setViewMode("row")}
                className={`px-2 py-0.5 text-[11px] font-bold rounded-md transition-all cursor-pointer ${
                  viewMode === "row"
                    ? "bg-white text-sky-950 shadow-xs border border-sky-300 font-extrabold"
                    : "text-gray-600 hover:text-gray-900 border border-transparent"
                }`}
                title="Single Horizontal Row per video with mouse wheel scroll (No arrows, sequences separated)"
              >
                ↔ Single Row
              </button>
              <button
                type="button"
                onClick={() => setViewMode("grouped")}
                className={`px-2 py-0.5 text-[11px] font-bold rounded-md transition-all cursor-pointer ${
                  viewMode === "grouped"
                    ? "bg-white text-sky-950 shadow-xs border border-sky-300 font-extrabold"
                    : "text-gray-600 hover:text-gray-900 border border-transparent"
                }`}
                title="Grouped stack cards per video with sequence pagination (Show More / Show All / Collapse)"
              >
                📑 Stack Cards
              </button>
              <button
                type="button"
                onClick={() => setViewMode("flat")}
                className={`px-2 py-0.5 text-[11px] font-bold rounded-md transition-all cursor-pointer ${
                  viewMode === "flat"
                    ? "bg-white text-sky-950 shadow-xs border border-sky-300 font-extrabold"
                    : "text-gray-600 hover:text-gray-900 border border-transparent"
                }`}
                title="Display in traditional flat grid"
              >
                ▦ Flat Grid
              </button>
            </div>
          </div>
        )}

        {/* Home Button */}
        <button
          onClick={goToFirstPage}
          disabled={!hasPrevPage}
          className={`p-1.5 rounded-lg border flex items-center justify-center transition-all ${
            hasPrevPage
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
          disabled={!hasPrevPage}
          className={`p-1.5 rounded-lg border flex items-center justify-center transition-all ${
            hasPrevPage
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
          <span className="text-blue-700 font-extrabold text-sm">{currentPage}</span>
          {totalPages > 1 && (
            <span className="text-gray-400 font-normal text-[11px]">/ {totalPages}</span>
          )}
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
        ocr_weight: params.ocr_weight !== undefined ? params.ocr_weight : 0.0,
        asr_weight: params.asr_weight !== undefined ? params.asr_weight : 0.0,
        nprobe: params.nprobe ?? 32,
        limit: params.limit ?? 20,
        temporal_k: params.temporal_k ?? 200,
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
        className="w-full flex flex-col shrink-0 overflow-y-auto min-h-0"
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
          }}
          excludeVideos={excludeVideos}
          onExcludeVideosChange={(val) => {
            setExcludeVideos(val);
          }}
          onApplyVideoFilters={(newInc, newExc) => {
            setIncludeVideos(newInc);
            setExcludeVideos(newExc);
            setAppliedInclude(newInc);
            setAppliedExclude(newExc);
            setLocalOffset(0);
          }}
          isSearching={isSearching}
          onCancelSearch={handleCancelSearch}
          onResetQueryHeight={handleResetQueryHeight}
          translationFailed={!!data?.translation_failed}
          collection={collection}
          onCollectionChange={handleCollectionChange}
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

        {/* Frame Results Grid / Grouped Video Cards */}
        {displayFrames.length === 0 ? (
          <div className="w-full text-center p-8 bg-white border border-gray-300 rounded text-gray-500 text-sm font-medium">
            {isSearching ? "Searching keyframes..." : "No keyframes found. Check your search query or video filter parameters."}
          </div>
        ) : isTemporalResult && viewMode === "row" ? (
          /* Mode 1: Single Horizontal Row per Video with mouse wheel scroll & distinct sequence boxes (No Arrows) */
          <div className={`flex flex-col gap-3 ${isSearching ? "animate-pulse" : ""}`}>
            {groupedVideos.map((videoGroup) => {
              const totalSeqs = videoGroup.sequences.length;

              return (
                <div
                  key={videoGroup.video_id}
                  className="bg-white border border-sky-200 rounded-xl p-2.5 shadow-xs flex flex-col gap-2 transition-all hover:border-sky-400 hover:shadow-sm"
                >
                  {/* Video Row Header */}
                  <div className="flex items-center justify-between flex-wrap gap-2 pb-1.5 border-b border-sky-100 bg-gradient-to-r from-sky-50/80 to-transparent -mx-2.5 -mt-2.5 p-2.5 rounded-t-xl">
                    <div className="flex items-center gap-2 flex-wrap">
                      <div className="flex items-center gap-1.5 bg-sky-800 text-white font-mono font-extrabold text-xs px-2.5 py-1 rounded-lg shadow-xs">
                        <span>🎥</span>
                        <span>{videoGroup.video_id}</span>
                      </div>
                      <span className="text-[11px] font-semibold text-gray-700">
                        Best Score: <strong className="text-emerald-700 font-mono font-bold">{(videoGroup.maxScore || 0).toFixed(4)}</strong>
                      </span>
                      <span className="text-gray-300">•</span>
                      <span className="text-[11px] text-sky-800 bg-sky-100/90 border border-sky-200 font-bold px-2 py-0.5 rounded-full font-mono">
                        {totalSeqs} {totalSeqs === 1 ? "sequence" : "sequences"}
                      </span>
                    </div>

                    {/* Video Quick Actions */}
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => {
                          const firstFrame = videoGroup.sequences[0]?.time_line?.[0] || videoGroup.sequences[0]?.frame_id;
                          playVideo({ video_id: videoGroup.video_id, frame_id: firstFrame }, firstFrame);
                        }}
                        className="text-[11px] font-bold px-2.5 py-1 rounded bg-blue-600 hover:bg-blue-700 text-white shadow-xs flex items-center gap-1 transition-colors cursor-pointer"
                        title="Play video from start of sequence"
                      >
                        <span>▶ Play</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => handleAddIncludeVideo(videoGroup.video_id)}
                        className="text-[10px] font-semibold px-2 py-1 rounded bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-300 transition-colors cursor-pointer"
                        title="Filter: Include this video"
                      >
                        + Inc
                      </button>

                      <button
                        type="button"
                        onClick={() => handleAddExcludeVideo(videoGroup.video_id)}
                        className="text-[10px] font-semibold px-2 py-1 rounded bg-rose-50 hover:bg-rose-100 text-rose-800 border border-rose-300 transition-colors cursor-pointer"
                        title="Filter: Exclude this video"
                      >
                        - Exc
                      </button>
                    </div>
                  </div>

                  {/* Horizontal Sequences Row with Mouse Wheel Scroll Support (Prevent parent page vertical scrolling) */}
                  <HorizontalWheelScroll className="flex flex-row items-stretch gap-3 overflow-x-auto pb-2 pt-0.5 scrollbar-thin">
                    {videoGroup.sequences.map((seq, seqIdx) => {
                      const keyframesList = seq.time_line || [seq.frame_id];
                      const scoresList = seq.time_line_scores || [];
                      const seqScore = seq.scores?.final ?? 0;

                      return (
                        <div
                          key={seqIdx}
                          className="shrink-0 flex flex-col bg-slate-50/95 border-2 border-sky-300/80 hover:border-sky-500 rounded-xl p-2 shadow-xs transition-all"
                        >
                          {/* Sequence Sub-Header */}
                          <div className="flex items-center justify-between gap-2 pb-1.5 mb-1.5 border-b border-sky-200/70 text-[10px]">
                            <div className="flex items-center gap-1.5">
                              <span className="font-mono font-extrabold text-sky-950 bg-sky-200 px-1.5 py-0.5 rounded">
                                Seq #{seqIdx + 1}
                              </span>
                              <span className="text-gray-600 font-mono">
                                Score: <strong className="text-blue-700 font-bold">{seqScore.toFixed(4)}</strong>
                              </span>
                            </div>
                            <span className="font-mono text-gray-500 font-bold">
                              {keyframesList.length} Steps
                            </span>
                          </div>

                          {/* Step Cards placed side-by-side with NO arrows */}
                          <div className="flex flex-row items-center gap-1.5">
                            {keyframesList.map((kf, kfIdx) => {
                              const sc = (scoresList && scoresList[kfIdx]) || seq.scores;
                              const frameKey = `${videoGroup.video_id}#${kf}`;

                              return (
                                <div
                                  key={`${frameKey}-${seqIdx}-${kfIdx}`}
                                  className="w-40 sm:w-44 md:w-48 shrink-0 flex flex-col"
                                >
                                  <FrameItem
                                    id={frameKey}
                                    video_id={videoGroup.video_id}
                                    frame_id={kf}
                                    thumbnail={`http://127.0.0.1:6900/api/files/${videoGroup.video_id}/${kf}`}
                                    scores={sc}
                                    ocr={seq.ocr}
                                    temporalStep={`Step ${kfIdx + 1}/${keyframesList.length}`}
                                    onPlay={() => playVideo({ video_id: videoGroup.video_id, frame_id: kf }, kf)}
                                    onSearchSimilar={() => handleSearchSimilar(frameKey)}
                                    onAddIncludeVideo={handleAddIncludeVideo}
                                    onAddExcludeVideo={handleAddExcludeVideo}
                                  />
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })}
                  </HorizontalWheelScroll>
                </div>
              );
            })}
          </div>
        ) : isTemporalResult && viewMode === "grouped" ? (
          /* Mode 2: Grouped Stack Cards (Sorted descending by highest sequence score, default 1 sequence) */
          <div className={`flex flex-col gap-3 ${isSearching ? "animate-pulse" : ""}`}>
            {groupedVideos.map((videoGroup) => {
              const totalSeqs = videoGroup.sequences.length;
              const visibleCount = expandedCounts[videoGroup.video_id] ?? 1;
              const visibleSequences = videoGroup.sequences.slice(0, visibleCount);

              return (
                <div
                  key={videoGroup.video_id}
                  className="bg-white border border-sky-200 rounded-xl p-3 shadow-xs flex flex-col gap-2.5 transition-all hover:border-sky-400 hover:shadow-sm"
                >
                  {/* Video Group Header */}
                  <div className="flex items-center justify-between flex-wrap gap-2 pb-2 border-b border-sky-100 bg-gradient-to-r from-sky-50/80 to-transparent -mx-3 -mt-3 p-3 rounded-t-xl">
                    <div className="flex items-center gap-2 flex-wrap">
                      <div className="flex items-center gap-1.5 bg-sky-800 text-white font-mono font-extrabold text-xs px-2.5 py-1 rounded-lg shadow-xs">
                        <span>🎥</span>
                        <span>{videoGroup.video_id}</span>
                      </div>
                      <span className="text-[11px] font-semibold text-gray-700">
                        Best Score: <strong className="text-emerald-700 font-mono font-bold">{(videoGroup.maxScore || 0).toFixed(4)}</strong>
                      </span>
                      <span className="text-gray-300">•</span>
                      <span className="text-[11px] text-sky-800 bg-sky-100/90 border border-sky-200 font-bold px-2 py-0.5 rounded-full font-mono">
                        {totalSeqs} {totalSeqs === 1 ? "sequence match" : "sequence matches"}
                      </span>
                    </div>

                    {/* Video Quick Actions */}
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => {
                          const firstFrame = videoGroup.sequences[0]?.time_line?.[0] || videoGroup.sequences[0]?.frame_id;
                          playVideo({ video_id: videoGroup.video_id, frame_id: firstFrame }, firstFrame);
                        }}
                        className="text-[11px] font-bold px-2.5 py-1 rounded bg-blue-600 hover:bg-blue-700 text-white shadow-xs flex items-center gap-1 transition-colors cursor-pointer"
                        title="Play video from start of sequence"
                      >
                        <span>▶ Play</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => handleAddIncludeVideo(videoGroup.video_id)}
                        className="text-[10px] font-semibold px-2 py-1 rounded bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-300 transition-colors cursor-pointer"
                        title="Filter: Include this video"
                      >
                        + Inc
                      </button>

                      <button
                        type="button"
                        onClick={() => handleAddExcludeVideo(videoGroup.video_id)}
                        className="text-[10px] font-semibold px-2 py-1 rounded bg-rose-50 hover:bg-rose-100 text-rose-800 border border-rose-300 transition-colors cursor-pointer"
                        title="Filter: Exclude this video"
                      >
                        - Exc
                      </button>
                    </div>
                  </div>

                  {/* Sequences in this Video (Default showing 1 sequence) */}
                  <div className="flex flex-col gap-2.5">
                    {visibleSequences.map((seq, seqIdx) => {
                      const keyframesList = seq.time_line || [seq.frame_id];
                      const scoresList = seq.time_line_scores || [];
                      const seqScore = seq.scores?.final ?? 0;

                      return (
                        <div
                          key={seqIdx}
                          className="flex flex-col gap-1.5 bg-slate-50/70 border border-gray-200/90 rounded-lg p-2 hover:border-sky-300 transition-colors"
                        >
                          {/* Sequence Sub-Header */}
                          <div className="flex items-center justify-between text-[11px]">
                            <div className="flex items-center gap-2">
                              <span className="font-mono font-extrabold text-sky-950 bg-sky-200/80 px-1.5 py-0.5 rounded text-[10px]">
                                Sequence #{seqIdx + 1}
                              </span>
                              <span className="text-gray-500 font-mono text-[10px]">
                                Score: <strong className="text-blue-700">{seqScore.toFixed(4)}</strong>
                              </span>
                            </div>
                            <span className="text-[10px] font-semibold text-gray-500 font-mono">
                              {keyframesList.length} Chronological Steps
                            </span>
                          </div>

                          {/* Horizontal Steps Cards with Arrow Connectors */}
                          <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-thin">
                            {keyframesList.map((kf, kfIdx) => {
                              const sc = (scoresList && scoresList[kfIdx]) || seq.scores;
                              const frameKey = `${videoGroup.video_id}#${kf}`;
                              const isLast = kfIdx === keyframesList.length - 1;

                              return (
                                <React.Fragment key={`${frameKey}-${seqIdx}-${kfIdx}`}>
                                  {/* Step Card Wrapper */}
                                  <div className="w-44 sm:w-48 md:w-52 shrink-0 flex flex-col">
                                    <FrameItem
                                      id={frameKey}
                                      video_id={videoGroup.video_id}
                                      frame_id={kf}
                                      thumbnail={`http://127.0.0.1:6900/api/files/${videoGroup.video_id}/${kf}`}
                                      scores={sc}
                                      ocr={seq.ocr}
                                      temporalStep={`Step ${kfIdx + 1}/${keyframesList.length}`}
                                      onPlay={() => playVideo({ video_id: videoGroup.video_id, frame_id: kf }, kf)}
                                      onSearchSimilar={() => handleSearchSimilar(frameKey)}
                                      onAddIncludeVideo={handleAddIncludeVideo}
                                      onAddExcludeVideo={handleAddExcludeVideo}
                                    />
                                  </div>

                                  {/* Flow Arrow Connector between steps */}
                                  {!isLast && (
                                    <div className="flex flex-col items-center justify-center px-1 text-sky-500 font-extrabold select-none shrink-0">
                                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                                      </svg>
                                    </div>
                                  )}
                                </React.Fragment>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Bottom Footer Controls: Show More Sequences, Show All, Collapse */}
                  {totalSeqs > 1 && (
                    <div className="flex items-center justify-between pt-1 border-t border-sky-100 mt-0.5 flex-wrap gap-1.5 bg-sky-50/40 px-2 py-1 rounded-md">
                      <span className="text-[11px] text-gray-600 font-mono">
                        Showing <strong className="text-sky-900 font-bold">{visibleCount}</strong> of <strong>{totalSeqs}</strong> sequences
                      </span>

                      <div className="flex items-center gap-1.5 flex-wrap">
                        {/* Show Next Sequence (+1) */}
                        {visibleCount < totalSeqs && (
                          <button
                            type="button"
                            onClick={() => handleShowMoreSeq(videoGroup.video_id, totalSeqs)}
                            className="text-[11px] font-bold px-2 py-0.5 rounded bg-white hover:bg-sky-100 text-sky-800 border border-sky-300 shadow-2xs flex items-center gap-1 cursor-pointer transition-colors"
                            title="Show the next matching sequence for this video"
                          >
                            <span>+ Show More</span>
                          </button>
                        )}

                        {/* Show All sequences */}
                        {visibleCount < totalSeqs && (
                          <button
                            type="button"
                            onClick={() => handleShowAllSeq(videoGroup.video_id, totalSeqs)}
                            className="text-[11px] font-bold px-2 py-0.5 rounded bg-indigo-50 hover:bg-indigo-100 text-indigo-800 border border-indigo-300 shadow-2xs flex items-center gap-1 cursor-pointer transition-colors"
                            title={`Show all ${totalSeqs} sequences for this video`}
                          >
                            <span>Show All ({totalSeqs})</span>
                          </button>
                        )}

                        {/* Collapse */}
                        {visibleCount > 1 && (
                          <button
                            type="button"
                            onClick={() => handleCollapseSeq(videoGroup.video_id)}
                            className="text-[11px] font-semibold px-2 py-0.5 rounded bg-gray-100 hover:bg-gray-200 text-gray-700 border border-gray-300 shadow-2xs flex items-center gap-1 cursor-pointer transition-colors"
                            title="Collapse to show only the top sequence"
                          >
                            <span>▴ Collapse</span>
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          /* Standard Flat Grid (for Single Search or Flat View Mode) */
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
