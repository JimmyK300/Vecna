const CORE_PORT =
  (typeof import.meta !== "undefined" && import.meta.env && import.meta.env.VITE_PORT) || 6900;

export function teamworkWebSocketUrl() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const host = window.location.hostname || "127.0.0.1";
  return `${protocol}://${host}:${CORE_PORT}/ws/team`;
}

export function connectTeamwork({ onSync, onStatus, onError } = {}) {
  let closedByUser = false;
  let socket = null;
  let reconnectTimer = null;

  const connect = () => {
    if (closedByUser) return;
    onStatus?.("connecting");
    socket = new WebSocket(teamworkWebSocketUrl());

    socket.onopen = () => onStatus?.("connected");
    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message?.type === "team_sync" && Array.isArray(message.data)) {
          onSync?.(message.data);
        } else if (message?.type === "error") {
          onError?.(message.data?.detail || "Teamwork server error");
        }
      } catch (error) {
        onError?.("Invalid teamwork message");
      }
    };
    socket.onerror = () => onStatus?.("error");
    socket.onclose = () => {
      onStatus?.("disconnected");
      if (!closedByUser) {
        reconnectTimer = window.setTimeout(connect, 1000);
      }
    };
  };

  connect();

  const send = (type, data = {}) => {
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify({ type, data }));
    return true;
  };

  return {
    addFrame(frameId, sender = "", note = "") {
      return send("add_frame", { frame_id: frameId, sender, note });
    },
    removeFrame(frameId) {
      return send("remove_frame", { frame_id: frameId });
    },
    clear() {
      return send("clear_panel", {});
    },
    close() {
      closedByUser = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      socket?.close();
    },
  };
}
