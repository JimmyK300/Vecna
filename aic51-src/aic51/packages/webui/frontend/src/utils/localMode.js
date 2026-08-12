export const EVENT_RETRIEVAL_ENABLED = import.meta.env?.VITE_ENABLE_EVENT_RETRIEVAL === "true";

export function isExternalSubmissionEnabled() {
  return EVENT_RETRIEVAL_ENABLED;
}
