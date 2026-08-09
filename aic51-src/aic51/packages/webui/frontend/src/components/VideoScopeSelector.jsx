import React, { useEffect, useMemo, useRef, useState } from "react";
import { getVideoInventory } from "../services/search.js";

function matchesTokens(videoId, rawTokens) {
  const tokens = String(rawTokens || "")
    .split(/[,;\s]+/)
    .map((token) => token.trim().toLowerCase())
    .filter(Boolean);
  if (tokens.length === 0) return false;
  const id = String(videoId).toLowerCase();
  return tokens.some((token) => id.includes(token));
}

function GroupToggle({ checked, indeterminate, onChange, label, count }) {
  const ref = useRef(null);

  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);

  return (
    <label className="flex items-center gap-1 min-w-0 cursor-pointer text-[10px] font-bold text-gray-800">
      <input
        ref={ref}
        type="checkbox"
        checked={checked}
        onChange={onChange}
        className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
      />
      <span className="truncate" title={label}>{label}</span>
      <span className="text-gray-400 font-mono shrink-0">({count})</span>
    </label>
  );
}

export default function VideoScopeSelector({
  includeVideos = "",
  excludeVideos = "",
  onScopeChange,
  onIncludeVideosChange,
  onExcludeVideosChange,
  groups = [],
}) {
  const [videos, setVideos] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [searchText, setSearchText] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let alive = true;
    getVideoInventory()
      .then((items) => {
        if (!alive) return;
        const nextVideos = [...items].sort((a, b) => a.localeCompare(b));
        setVideos(nextVideos);
        setLoadError("");

        let initial;
        if (String(includeVideos || "").trim()) {
          initial = new Set(nextVideos.filter((id) => matchesTokens(id, includeVideos)));
        } else if (String(excludeVideos || "").trim()) {
          initial = new Set(nextVideos.filter((id) => !matchesTokens(id, excludeVideos)));
        } else {
          initial = new Set(nextVideos);
        }
        setSelected(initial);
      })
      .catch((err) => {
        if (!alive) return;
        console.error("Failed to load video inventory:", err);
        setLoadError("Video inventory unavailable");
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (videos.length === 0) return;
    if (String(includeVideos || "").trim()) {
      setSelected(new Set(videos.filter((id) => matchesTokens(id, includeVideos))));
    } else if (String(excludeVideos || "").trim()) {
      setSelected(new Set(videos.filter((id) => !matchesTokens(id, excludeVideos))));
    } else {
      setSelected(new Set(videos));
    }
  }, [includeVideos, excludeVideos, videos]);

  const groupedVideos = useMemo(() => {
    const knownGroups = groups.map((group) => ({ ...group, videos: [] }));
    const other = { prefix: "__other__", name: "Other", videos: [] };

    videos.forEach((videoId) => {
      const match = knownGroups.find((group) => videoId.startsWith(group.prefix));
      (match || other).videos.push(videoId);
    });

    return [
      ...knownGroups.filter((group) => group.videos.length > 0),
      ...(other.videos.length ? [other] : []),
    ];
  }, [videos, groups]);

  const filteredGroups = useMemo(() => {
    const needle = searchText.trim().toLowerCase();
    if (!needle) return groupedVideos;
    return groupedVideos
      .map((group) => ({
        ...group,
        videos: group.videos.filter((id) => id.toLowerCase().includes(needle)),
      }))
      .filter((group) => group.videos.length > 0);
  }, [groupedVideos, searchText]);

  const publishScope = (include, exclude) => {
    if (onScopeChange) {
      onScopeChange({ includeVideos: include, excludeVideos: exclude });
      return;
    }
    onIncludeVideosChange?.(include);
    onExcludeVideosChange?.(exclude);
  };

  const commitSelection = (nextSelected) => {
    setSelected(nextSelected);
    if (videos.length === 0) return;

    if (nextSelected.size === videos.length) {
      publishScope("", "");
      return;
    }

    if (nextSelected.size === 0) {
      publishScope("__none__", "");
      return;
    }

    const selectedIds = videos.filter((id) => nextSelected.has(id));
    const unselectedIds = videos.filter((id) => !nextSelected.has(id));
    if (selectedIds.length <= unselectedIds.length) {
      publishScope(selectedIds.join(","), "");
    } else {
      publishScope("", unselectedIds.join(","));
    }
  };

  const toggleVideo = (videoId) => {
    const next = new Set(selected);
    if (next.has(videoId)) next.delete(videoId);
    else next.add(videoId);
    commitSelection(next);
  };

  const toggleGroup = (videoIds) => {
    const allSelected = videoIds.every((id) => selected.has(id));
    const next = new Set(selected);
    videoIds.forEach((id) => {
      if (allSelected) next.delete(id);
      else next.add(id);
    });
    commitSelection(next);
  };

  const summary =
    videos.length === 0
      ? "Loading videos…"
      : selected.size === videos.length
      ? `All ${videos.length} videos`
      : `${selected.size}/${videos.length} videos`;

  return (
    <div className="w-full lg:w-64 flex flex-col gap-1 bg-white border border-sky-300 p-2 rounded shadow-sm relative">
      <div className="flex items-center justify-between gap-2">
        <label className="text-xs font-bold text-gray-800 flex items-center gap-1 min-w-0">
          <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0"></span>
          <span className="truncate">Video scope</span>
        </label>
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="px-2 py-0.5 text-[10px] font-mono font-bold border border-gray-300 rounded bg-gray-50 hover:bg-gray-100 shrink-0"
        >
          {summary} {expanded ? "▲" : "▼"}
        </button>
      </div>

      {loadError && (
        <div className="text-[9px] text-red-700 bg-red-50 border border-red-200 rounded p-1">
          {loadError}. Existing raw scope values are preserved.
        </div>
      )}

      {expanded && videos.length > 0 && (
        <div className="absolute top-full right-0 mt-1 z-50 w-[min(32rem,90vw)] max-h-[70vh] bg-white border border-gray-300 rounded-lg shadow-2xl p-2 flex flex-col gap-2">
          <div className="flex gap-1">
            <input
              autoFocus
              type="search"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="Find video ID…"
              className="flex-1 min-w-0 border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none focus:border-emerald-500"
            />
            <button
              type="button"
              onClick={() => commitSelection(new Set(videos))}
              className="px-2 py-1 text-[10px] font-bold border border-emerald-300 text-emerald-800 bg-emerald-50 hover:bg-emerald-100 rounded"
            >
              Select all
            </button>
            <button
              type="button"
              onClick={() => commitSelection(new Set())}
              className="px-2 py-1 text-[10px] font-bold border border-gray-300 text-gray-700 bg-gray-50 hover:bg-gray-100 rounded"
            >
              Clear
            </button>
          </div>

          <div className="overflow-y-auto flex flex-col gap-2 pr-1">
            {filteredGroups.map((group) => {
              const selectedCount = group.videos.filter((id) => selected.has(id)).length;
              const allSelected = selectedCount === group.videos.length;
              const partiallySelected = selectedCount > 0 && !allSelected;
              return (
                <div key={group.prefix} className="border border-gray-200 rounded p-1.5 bg-gray-50/60">
                  <GroupToggle
                    checked={allSelected}
                    indeterminate={partiallySelected}
                    onChange={() => toggleGroup(group.videos)}
                    label={group.name}
                    count={group.videos.length}
                  />
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-1 mt-1 pl-4">
                    {group.videos.map((videoId) => (
                      <label key={videoId} className="flex items-center gap-1 text-[10px] font-mono cursor-pointer min-w-0">
                        <input
                          type="checkbox"
                          checked={selected.has(videoId)}
                          onChange={() => toggleVideo(videoId)}
                          className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                        />
                        <span className="truncate" title={videoId}>{videoId}</span>
                      </label>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="text-[9px] text-gray-500 font-mono border-t pt-1">
            All checked = search all. Small checked subsets serialize as includes; small unchecked subsets serialize as excludes.
          </div>
        </div>
      )}
    </div>
  );
}
