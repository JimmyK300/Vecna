function isBlocked(event, isInput) {
  return isInput || event?.metaKey || event?.ctrlKey || event?.altKey;
}

export function getSearchShortcutAction(event, { isInput = false } = {}) {
  if (isBlocked(event, isInput)) return null;
  const key = String(event?.key || "");
  const lowerKey = key.toLowerCase();

  if (event?.shiftKey && /^[0-9]$/.test(key)) {
    return { type: "quick-open", index: key === "0" ? 9 : Number(key) - 1 };
  }
  if (lowerKey === "j") return { type: "candidate-previous" };
  if (lowerKey === "k") return { type: "candidate-next" };
  if (lowerKey === "s") return { type: "toggle-shortlist" };
  if (lowerKey === "x") return { type: "toggle-reject" };
  if (event?.shiftKey && key === "/") return { type: "focus-answer" };
  if (key === "/") return { type: "focus-search" };
  if (key === "ArrowUp") return { type: "page-previous" };
  if (key === "ArrowDown") return { type: "page-next" };
  return null;
}

export function getVideoShortcutAction(event, { isInput = false } = {}) {
  if (isBlocked(event, isInput)) return null;
  const key = String(event?.key || "");

  if (event?.shiftKey && key === "/") return { type: "focus-answer" };
  if (key === "ArrowLeft") return { type: event.shiftKey ? "frame-previous" : "seek-previous" };
  if (key === "ArrowRight") return { type: event.shiftKey ? "frame-next" : "seek-next" };
  if (key === "[") return { type: "frame-previous" };
  if (key === "]") return { type: "frame-next" };
  if (key === "-") return { type: "speed-down" };
  if (key === "+" || key === "=") return { type: "speed-up" };
  if (key.toLowerCase() === "k") return { type: "toggle-play" };
  if (key.toLowerCase() === "s") return { type: "toggle-select-frame" };
  return null;
}

// Kept as a small compatibility mapper for callers outside the two surfaces.
export function getShortcutAction(event, options = {}) {
  return (options.context === "video" ? getVideoShortcutAction : getSearchShortcutAction)(event, options)?.type || null;
}
