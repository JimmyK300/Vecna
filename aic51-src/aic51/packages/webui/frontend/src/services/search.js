import axios from "axios";

const PORT = import.meta.env.VITE_PORT || 6900;

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
    q: q,
    offset: offset,
    limit: limit,
    nprobe: nprobe,
    temporal_k: temporal_k,
    ocr_weight: ocr_weight,
    asr_weight: asr_weight,
    max_interval: max_interval,
  };

  if (auto_translate) {
    params.auto_translate = auto_translate;
  }

  if (en_to_vi_translate) {
    params.en_to_vi_translate = en_to_vi_translate;
  }

  if (selected) {
    params.selected = selected;
  }

  if (target_features && target_features.length > 0) {
    params.target_features = target_features;
  }

  if (include_videos) {
    params.include_videos = include_videos;
  }

  if (exclude_videos) {
    params.exclude_videos = exclude_videos;
  }

  const res = await axios.get(`http://127.0.0.1:${PORT}/api/search_multimodal`, {
    params: params,
  });
  let data = res.data;

  // Strict Exclude & Include Video Filtering
  if (data && Array.isArray(data.frames)) {
    if (exclude_videos && String(exclude_videos).trim().length > 0) {
      const excludes = String(exclude_videos)
        .split(/[,;\s]+/)
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean);
      if (excludes.length > 0) {
        data.frames = data.frames.filter((frame) => {
          const vId = String(frame.video_id || "").toLowerCase();
          return !excludes.some((ex) => vId.includes(ex));
        });
      }
    }

    if (include_videos && String(include_videos).trim().length > 0) {
      const includes = String(include_videos)
        .split(/[,;\s]+/)
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean);
      if (includes.length > 0) {
        data.frames = data.frames.filter((frame) => {
          const vId = String(frame.video_id || "").toLowerCase();
          return includes.some((inc) => vId.includes(inc));
        });
      }
    }
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
    id: id,
    offset: offset,
    limit: limit,
    nprobe: nprobe,
    temporal_k: temporal_k,
    ocr_weight: ocr_weight,
    asr_weight: asr_weight,
    max_interval: max_interval,
  };

  if (target_features && target_features.length > 0) {
    params.target_features = target_features;
  }

  const res = await axios.get(`http://127.0.0.1:${PORT}/api/search_image`, {
    params: params,
  });
  const data = res.data;
  return data;
}

export async function getFrameInfo(videoId, frameId) {
  const res = await axios.get(`http://127.0.0.1:${PORT}/api/files/info/${videoId}/${frameId}`);
  const data = res.data;
  return data;
}

export async function getTargetFeatures() {
  const res = await axios.get(`http://127.0.0.1:${PORT}/api/target_features`);
  const data = res.data;
  return data;
}

export async function getVideoTranscript(videoId) {
  const res = await axios.get(`http://127.0.0.1:${PORT}/api/video/transcript/${videoId}`);
  const data = res.data;
  return data;
}

export async function getVideoKeyframes(videoId) {
  const res = await axios.get(`http://127.0.0.1:${PORT}/api/video/keyframes/${videoId}`);
  const data = res.data;
  return data;
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
