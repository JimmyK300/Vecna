import axios from "axios";

const PORT = import.meta.env.VITE_PORT || 6900;

function installThumbnailTimingProbe() {
  if (typeof window === "undefined" || window.__vecnaThumbnailTimingProbeInstalled) return;
  window.__vecnaThumbnailTimingProbeInstalled = true;
  window.addEventListener(
    "load",
    (event) => {
      const target = event.target;
      const perf = window.__vecnaSearchPerf;
      if (!perf || perf.firstThumbnailAt || target?.tagName !== "IMG") return;
      if (!String(target.src || "").includes("/api/files/")) return;

      perf.firstThumbnailAt = performance.now();
      console.debug(
        `[Vecna search] first usable thumbnail ${(perf.firstThumbnailAt - perf.startedAt).toFixed(1)} ms from request; ` +
          `${(perf.firstThumbnailAt - perf.responseAt).toFixed(1)} ms after search response`
      );
    },
    true
  );
}

installThumbnailTimingProbe();

export async function search(
  q,
  offset,
  limit,
  nprobe,
  temporal_k,
  ocr_weight,
  asr_weight,
  max_interval,
  selected,
  target_features,
  auto_translate,
  include_videos,
  exclude_videos,
  en_to_vi_translate,
) {
  const params = {
    q,
    offset,
    limit,
    nprobe,
    temporal_k,
    ocr_weight,
    asr_weight,
    max_interval,
  };

  if (auto_translate) params.auto_translate = auto_translate;
  if (en_to_vi_translate) params.en_to_vi_translate = en_to_vi_translate;
  if (selected) params.selected = selected;
  if (target_features && target_features.length > 0) params.target_features = target_features;
  if (include_videos) params.include_videos = include_videos;
  if (exclude_videos) params.exclude_videos = exclude_videos;

  const startedAt = performance.now();
  const res = await axios.get(`http://127.0.0.1:${PORT}/api/search_multimodal`, {
    params,
  });
  const responseAt = performance.now();
  const data = res.data;
  const normalizedAt = performance.now();

  console.debug(
    `[Vecna search] response ${(responseAt - startedAt).toFixed(1)} ms; response normalize ${(normalizedAt - responseAt).toFixed(1)} ms`
  );

  if (typeof window !== "undefined" && Number(offset) === 0) {
    window.__vecnaSearchPerf = {
      startedAt,
      responseAt,
      transformedAt: normalizedAt,
      firstThumbnailAt: null,
    };

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const perf = window.__vecnaSearchPerf;
        if (!perf || perf.startedAt !== startedAt) return;
        perf.nextPaintAt = performance.now();
        console.debug(
          `[Vecna search] next browser paint ${(perf.nextPaintAt - normalizedAt).toFixed(1)} ms after response normalization`
        );
      });
    });
  }

  return data;
}

export async function searchSimilar(
  id,
  offset,
  limit,
  nprobe,
  temporal_k,
  ocr_weight,
  asr_weight,
  max_interval,
  target_features,
) {
  const params = {
    id,
    offset,
    limit,
    nprobe,
    temporal_k,
    ocr_weight,
    asr_weight,
    max_interval,
  };

  if (target_features && target_features.length > 0) params.target_features = target_features;

  const res = await axios.get(`http://127.0.0.1:${PORT}/api/search_image`, {
    params,
  });
  return res.data;
}

export async function getFrameInfo(videoId, frameId) {
  const res = await axios.get(`http://127.0.0.1:${PORT}/api/files/info/${videoId}/${frameId}`);
  return res.data;
}

export async function getTargetFeatures() {
  const res = await axios.get(`http://127.0.0.1:${PORT}/api/target_features`);
  return res.data;
}

export async function getVideoInventory() {
  const res = await axios.get(`http://127.0.0.1:${PORT}/api/videos`);
  const videos = res.data?.videos || [];
  return Array.isArray(videos) ? videos : [];
}

export async function getVideoTranscript(videoId) {
  const res = await axios.get(`http://127.0.0.1:${PORT}/api/video/transcript/${videoId}`);
  return res.data;
}

export async function getVideoKeyframes(videoId) {
  const res = await axios.get(`http://127.0.0.1:${PORT}/api/video/keyframes/${videoId}`);
  return res.data;
}

export async function getFrameOcr(videoId, frameId) {
  try {
    const res = await axios.get(`http://127.0.0.1:${PORT}/api/frame/ocr/${videoId}/${frameId}`);
    return res.data.ocr || "";
  } catch (err) {
    console.error(`Failed to fetch OCR for ${videoId} ${frameId}:`, err);
    return "";
  }
}
