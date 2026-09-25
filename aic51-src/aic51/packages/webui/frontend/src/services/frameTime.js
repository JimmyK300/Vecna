// The sparse map contains PTS values measured from the MP4 served to the player.
// Interpolation is only an estimate between mapped frames; mapped frames are exact.
export function timeAtFrameIndex(frameIndex, map, fps) {
  if (!Number.isFinite(frameIndex)) return 0;
  if (!Array.isArray(map) || map.length === 0) return frameIndex / fps;
  let lo = 0;
  let hi = map.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (map[mid].raw_idx < frameIndex) lo = mid + 1;
    else hi = mid;
  }
  if (lo < map.length && map[lo].raw_idx === frameIndex) return map[lo].pts_time;
  const prev = map[Math.max(0, lo - 1)];
  const next = map[Math.min(map.length - 1, lo)];
  if (prev === next) return Math.max(0, prev.pts_time + (frameIndex - prev.raw_idx) / fps);
  return prev.pts_time + (frameIndex - prev.raw_idx) *
    (next.pts_time - prev.pts_time) / (next.raw_idx - prev.raw_idx);
}

export function frameIndexAtTime(time, map, fps) {
  if (!Number.isFinite(time)) return 0;
  if (!Array.isArray(map) || map.length === 0) return Math.max(0, Math.round(time * fps));
  let lo = 0;
  let hi = map.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (map[mid].pts_time < time) lo = mid + 1;
    else hi = mid;
  }
  if (lo < map.length && map[lo].pts_time === time) return map[lo].raw_idx;
  const prev = map[Math.max(0, lo - 1)];
  const next = map[Math.min(map.length - 1, lo)];
  if (prev === next) return Math.max(0, Math.round(prev.raw_idx + (time - prev.pts_time) * fps));
  if (next.pts_time === prev.pts_time) return prev.raw_idx;
  return Math.max(0, Math.round(prev.raw_idx + (time - prev.pts_time) *
    (next.raw_idx - prev.raw_idx) / (next.pts_time - prev.pts_time)));
}
