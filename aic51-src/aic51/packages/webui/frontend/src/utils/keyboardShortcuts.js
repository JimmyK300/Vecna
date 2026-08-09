export function getShortcutAction(event, { isInput = false } = {}) {
  if (isInput || event?.metaKey || event?.ctrlKey || event?.altKey) return null;
  const key = String(event?.key || "");
  const lowerKey = key.toLowerCase();

  if (event?.shiftKey && key === "/") return "focus-answer";
  if (key === "/") return "focus-search";
  if (key === "ArrowUp") return "page-previous";
  if (key === "ArrowDown") return "page-next";
  if (key === "ArrowLeft") return event.shiftKey ? "frame-previous" : "seek-previous";
  if (key === "ArrowRight") return event.shiftKey ? "frame-next" : "seek-next";
  if (key === "[") return "frame-previous";
  if (key === "]") return "frame-next";
  if (key === "-") return "speed-down";
  if (key === "+" || key === "=") return "speed-up";
  if (lowerKey === "j") return "seek-previous";
  if (lowerKey === "k") return "toggle-play";
  if (lowerKey === "s") return "toggle-shortlist";
  if (lowerKey === "x") return "toggle-reject";
  return null;
}
