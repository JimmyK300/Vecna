import React, { useCallback, useEffect, useRef, useState } from "react";
import { useLoaderData, useNavigation, useOutletContext, useSubmit } from "react-router-dom";
import { search } from "../services/search.js";
import { AdvanceQueryContainer } from "../components/AdvanceQuery.jsx";
import { FrameItem, FrameContainer } from "../components/Frame.jsx";
import { usePlayVideo } from "../components/VideoPlayer.jsx";

export async function loader({ request }) {
  const url = new URL(request.url);
  const searchParams = url.searchParams;

  const q = searchParams.get("q") || "";
  const _offset = parseInt(searchParams.get("offset") || "0", 10);
  const limit = parseInt(searchParams.get("limit") || "20", 10);
  const nprobe = parseInt(searchParams.get("nprobe") || "32", 10);
  const temporal_k = parseInt(searchParams.get("temporal_k") || "10000", 10);
  const ocr_weight = parseFloat(searchParams.get("ocr_weight") || "0.5");
  const asr_weight = parseFloat(searchParams.get("asr_weight") || "0.0");
  const max_interval = parseInt(searchParams.get("max_interval") || "1000", 10);
  const auto_translate = searchParams.get("auto_translate") === "true";
  const en_to_vi_translate = searchParams.get("en_to_vi_translate") === "true";
  const target_features = searchParams.get("target_features") || "";
  const include_videos = searchParams.get("include_videos") || "";
  const exclude_videos = searchParams.get("exclude_videos") || "";

  const params = {
    limit,
    nprobe,
    temporal_k,
    ocr_weight,
    asr_weight,
    max_interval,
    auto_translate,
    en_to_vi_translate,
    target_features,
    include_videos,
    exclude_videos,
  };

  if (!q && !include_videos) {
    return {
      query: { q: "" },
      params,
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
      params,
      offset: res.offset || _offset,
      data: { total: res.total || 0, frames: res.frames || [] },
    };
  } catch (err) {
    console.error("Search failed:", err);
    return {
      query: { q },
      params,
      offset: _offset,
      data: { total: 0, frames: [] },
      error: err.message,
    };
  }
}

function filterFrames(frames, includeVideos, excludeVideos) {
  let displayFrames = frames;

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

  return displayFrames;
}

export default function Search() {
  const { query, params, offset, data } = useLoaderData();
  const { selectedFeatures } = useOutletContext();
  const submit = useSubmit();
  const navigation = useNavigation();
  const playVideo = usePlayVideo();

  const [searchQuery, setSearchQuery] = useState(query.q || "");
  const [autoTranslate, setAutoTranslate] = useState(params.auto_translate || false);
  const [enToViTranslate, setEnToViTranslate] = useState(params.en_to_vi_translate || false);
  const [includeVideos, setIncludeVideos] = useState(params.include_videos || "");
  const [excludeVideos, setExcludeVideos] = useState(params.exclude_videos || "");
  const [queryHeight, setQueryHeight] = useState(null);
  const [isResizingQuery, setIsResizingQuery] = useState(false);

  const limit = parseInt(params.limit || "20", 10);
  const initialFrames = (data && data.frames) || [];
  const [streamFrames, setStreamFrames] = useState(initialFrames);
  const [streamTotal, setStreamTotal] = useState(data.total || 0);
  const [nextOffset, setNextOffset] = useState((offset || 0) + limit);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(
    initialFrames.length >= limit && ((offset || 0) + limit < (data.total || Infinity))
  );

  const resultsContainerRef = useRef(null);
  const loadSentinelRef = useRef(null);
  const isSearching = navigation.state === "loading";

  useEffect(() => {
    setSearchQuery(query.q || "");
    setAutoTranslate(params.auto_translate || false);
    setEnToViTranslate(params.en_to_vi_translate || false);
    setIncludeVideos(params.include_videos || "");
    setExcludeVideos(params.exclude_videos || "");

    const frames = (data && data.frames) || [];
    setStreamFrames(frames);
    setStreamTotal(data.total || 0);
    setNextOffset((offset || 0) + limit);
    setHasMore(
      frames.length >= limit && ((offset || 0) + limit < (data.total || Infinity))
    );
    setIsLoadingMore(false);

    if (resultsContainerRef.current) resultsContainerRef.current.scrollTop = 0;
  }, [query.q, params, data, offset, limit]);

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
        setQueryHeight(Math.min(Math.max(70, e.clientY - rect.top), maxH));
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
    submit(
      {
        q: newQ,
        auto_translate: autoTranslate ? "true" : "false",
        en_to_vi_translate: enToViTranslate ? "true" : "false",
        include_videos: newInc,
        exclude_videos: newExc,
        target_features: (selectedFeatures || []).join(","),
        ocr_weight: params.ocr_weight ?? 0.5,
        asr_weight: params.asr_weight ?? 0.0,
        nprobe: params.nprobe || 32,
        limit: params.limit || 20,
        temporal_k: params.temporal_k || 10000,
        max_interval: params.max_interval || 1000,
        offset: 0,
      },
      { method: "get", action: "/search" }
    );
  };

  const loadMore = useCallback(async () => {
    if (isLoadingMore || !hasMore || (!query.q && !includeVideos)) return;

    setIsLoadingMore(true);
    const startedAt = performance.now();
    try {
      const res = await search(
        query.q,
        nextOffset,
        limit,
        params.nprobe || 32,
        params.temporal_k || 10000,
        params.ocr_weight ?? 0.5,
        params.asr_weight ?? 0.0,
        params.max_interval || 1000,
        undefined,
        (selectedFeatures || []).join(",") || params.target_features || "",
        params.auto_translate || false,
        includeVideos,
        excludeVideos,
        params.en_to_vi_translate || false
      );

      const incoming = res.frames || [];
      setStreamFrames((prev) => {
        const seen = new Set(
          prev.map((frame) => `${frame.video_id}#${frame.frame_id}#${JSON.stringify(frame.time_line || [])}`)
        );
        const unique = incoming.filter((frame) => {
          const key = `${frame.video_id}#${frame.frame_id}#${JSON.stringify(frame.time_line || [])}`;
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
        return [...prev, ...unique];
      });

      const total = res.total || streamTotal;
      const followingOffset = nextOffset + limit;
      setStreamTotal(total);
      setNextOffset(followingOffset);
      setHasMore(incoming.length >= limit && followingOffset < (total || Infinity));
      console.debug(
        `[Vecna search] fetched offset ${nextOffset} in ${(performance.now() - startedAt).toFixed(1)} ms`
      );
    } catch (err) {
      console.error("Failed to load more search results:", err);
      setHasMore(false);
    } finally {
      setIsLoadingMore(false);
    }
  }, [
    isLoadingMore,
    hasMore,
    query.q,
    includeVideos,
    excludeVideos,
    nextOffset,
    limit,
    params,
    selectedFeatures,
    streamTotal,
  ]);

  useEffect(() => {
    const sentinel = loadSentinelRef.current;
    const root = resultsContainerRef.current;
    if (!sentinel || !root || !hasMore) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) loadMore();
      },
      { root, rootMargin: "900px 0px", threshold: 0.01 }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadMore, hasMore]);

  const displayFrames = filterFrames(streamFrames, includeVideos, excludeVideos);

  useEffect(() => {
    const handleGlobalKeyDown = (e) => {
      const activeEl = document.activeElement;
      const isInInput = activeEl && ["INPUT", "TEXTAREA", "SELECT"].includes(activeEl.tagName);

      if (e.shiftKey && e.key === "Enter") {
        const submitBtn = document.getElementById("submit-selected-btn");
        if (submitBtn) {
          e.preventDefault();
          submitBtn.click();
          return;
        }
      }

      if (e.key === "/" && !isInInput) {
        e.preventDefault();
        const mainInput = document.querySelector('[data-query-input="main"]');
        if (mainInput) {
          mainInput.scrollIntoView({ behavior: "smooth", block: "center" });
          mainInput.focus();
        }
        return;
      }

      if (e.shiftKey && (e.key === "?" || e.key === "/")) {
        e.preventDefault();
        const answerSection = document.getElementById("answer-sidebar-container");
        if (answerSection) answerSection.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }

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

      if (isInInput) return;

      if (e.shiftKey && e.code && e.code.startsWith("Digit")) {
        const digit = parseInt(e.code.replace("Digit", ""), 10);
        const targetIdx = digit === 0 ? 9 : digit - 1;
        if (targetIdx < displayFrames.length) {
          e.preventDefault();
          const targetFrame = displayFrames[targetIdx];
          const kf = targetFrame.time_line ? targetFrame.time_line[0] : targetFrame.frame_id;
          playVideo({ video_id: targetFrame.video_id, frame_id: kf }, kf);
        }
      }
    };

    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, [displayFrames, playVideo]);

  const handleSearchSimilar = (frameKey) => {
    submit(
      {
        id: frameKey,
        target_features: (selectedFeatures || []).join(","),
        ocr_weight: params.ocr_weight ?? 0.5,
        asr_weight: params.asr_weight ?? 0.0,
        nprobe: params.nprobe || 32,
        limit: params.limit || 20,
        temporal_k: params.temporal_k || 10000,
        max_interval: params.max_interval || 1000,
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
            triggerSearch(searchQuery, val, excludeVideos);
          }}
          excludeVideos={excludeVideos}
          onExcludeVideosChange={(val) => {
            setExcludeVideos(val);
            triggerSearch(searchQuery, includeVideos, val);
          }}
          onVideoScopeChange={({ includeVideos: nextInc, excludeVideos: nextExc }) => {
            setIncludeVideos(nextInc);
            setExcludeVideos(nextExc);
            triggerSearch(searchQuery, nextInc, nextExc);
          }}
          isSearching={isSearching}
        />
      </div>

      <div
        onMouseDown={handleQueryMouseDown}
        className={`h-1.5 hover:h-1.5 w-full bg-gray-300 hover:bg-blue-500 cursor-row-resize select-none flex items-center justify-center transition-colors shrink-0 my-1 z-20 ${
          isResizingQuery ? "bg-blue-600" : ""
        }`}
        title="Drag up / down to resize Query Box"
      />

      <div ref={resultsContainerRef} className="flex-1 flex flex-col gap-2 min-h-0 overflow-y-auto pr-1">
        <div className="sticky top-0 z-20 self-end bg-white/90 backdrop-blur border border-gray-200 rounded px-2 py-1 text-[10px] font-mono text-gray-600 shadow-sm">
          <strong className="text-emerald-700">{displayFrames.length}</strong> loaded
          {streamTotal > 0 && <span> · {streamTotal} backend total</span>}
          {isLoadingMore && <span className="text-blue-700 animate-pulse"> · loading more…</span>}
        </div>

        {displayFrames.length === 0 ? (
          <div className="w-full text-center p-8 bg-white border border-gray-300 rounded text-gray-500 text-sm font-medium">
            {isSearching ? "Searching keyframes..." : "No keyframes found. Check your search query or video scope."}
          </div>
        ) : (
          <div className={isSearching ? "animate-pulse" : ""}>
            <FrameContainer id="result">
              {displayFrames.flatMap((frame, idx) => {
                const keyframesList = frame.time_line || [frame.frame_id];
                const scoresList = frame.time_line_scores || [];
                const isTemporalSeq = keyframesList.length > 1;

                return keyframesList.map((kf, kfIdx) => {
                  const sc = (scoresList && scoresList[kfIdx]) || frame.scores;
                  const frameKey = `${frame.video_id}#${kf}`;
                  return (
                    <div
                      key={`${frameKey}-${idx}-${kfIdx}`}
                      style={{ contentVisibility: "auto", containIntrinsicSize: "170px" }}
                    >
                      <FrameItem
                        id={frameKey}
                        video_id={frame.video_id}
                        frame_id={kf}
                        thumbnail={`http://127.0.0.1:6900/api/files/${frame.video_id}/${kf}`}
                        scores={sc}
                        ocr={frame.ocr}
                        temporalStep={isTemporalSeq ? `${kfIdx + 1}/${keyframesList.length}` : null}
                        onPlay={() => playVideo({ video_id: frame.video_id, frame_id: kf }, kf)}
                        onSearchSimilar={() => handleSearchSimilar(frameKey)}
                      />
                    </div>
                  );
                });
              })}
            </FrameContainer>
          </div>
        )}

        <div ref={loadSentinelRef} className="min-h-8 flex items-center justify-center text-[10px] font-mono text-gray-500 py-2">
          {isLoadingMore
            ? "Loading next result tranche…"
            : hasMore
            ? "Scroll to continue"
            : displayFrames.length > 0
            ? "End of results"
            : ""}
        </div>
      </div>
    </div>
  );
}
