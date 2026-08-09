const EVIDENCE_FIELDS = [
  "ocr",
  "asr",
  "ocr_bboxes",
  "ocr_boxes",
  "bboxes",
  "evidence",
];

function hasEvidenceValue(value) {
  if (value === undefined || value === null) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

export function mergeFrameEvidence(candidate = {}, frameInfo = {}) {
  const merged = { ...candidate, ...frameInfo };
  EVIDENCE_FIELDS.forEach((field) => {
    if (!hasEvidenceValue(frameInfo[field]) && hasEvidenceValue(candidate[field])) {
      merged[field] = candidate[field];
    }
  });
  return merged;
}

export function hasFrameOcrEvidence(frameInfo = {}) {
  return EVIDENCE_FIELDS.some((field) => {
    return hasEvidenceValue(frameInfo[field]);
  });
}

export function applyFrameOcrFallback(frameInfo = {}, fallback = {}) {
  return mergeFrameEvidence(frameInfo, fallback);
}
