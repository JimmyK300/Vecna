import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { useSelected } from "../components/SelectedProvider.jsx";
import { connectTeamwork } from "../services/teamwork.js";

export default function Team() {
  const { selected } = useSelected();
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("connecting");
  const [error, setError] = useState("");
  const [sender, setSender] = useState(() => localStorage.getItem("vecna_team_sender") || "");
  const [note, setNote] = useState("");
  const clientRef = useRef(null);

  useEffect(() => {
    const client = connectTeamwork({
      onSync: (next) => {
        setItems(next);
        setError("");
      },
      onStatus: setStatus,
      onError: setError,
    });
    clientRef.current = client;
    return () => {
      client.close();
      clientRef.current = null;
    };
  }, []);

  useEffect(() => {
    localStorage.setItem("vecna_team_sender", sender);
  }, [sender]);

  const selectedUnique = useMemo(() => Array.from(new Set(selected || [])), [selected]);

  const publishSelected = () => {
    if (!clientRef.current || selectedUnique.length === 0) return;
    for (const frameId of selectedUnique) {
      clientRef.current.addFrame(frameId, sender, note);
    }
    setNote("");
  };

  const statusClass =
    status === "connected"
      ? "bg-emerald-100 text-emerald-800 border-emerald-300"
      : status === "connecting"
      ? "bg-amber-100 text-amber-800 border-amber-300"
      : "bg-rose-100 text-rose-800 border-rose-300";

  return (
    <div className="flex flex-col w-full h-full min-h-0 overflow-hidden bg-slate-50">
      <div className="shrink-0 border-b border-slate-200 bg-white px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-lg font-extrabold text-slate-900">Team Shortlist</h1>
            <span className={`text-[11px] font-bold border rounded-full px-2 py-0.5 ${statusClass}`}>
              {status}
            </span>
            <span className="text-[11px] text-slate-500 font-mono">process-local realtime v1</span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Explicitly publish selected Vecna frames to every teammate connected to this core server.
          </p>
        </div>
        <Link
          to="/search"
          className="text-xs font-bold px-3 py-1.5 rounded-lg bg-slate-900 text-white hover:bg-slate-700"
        >
          ← Main search
        </Link>
      </div>

      <div className="shrink-0 px-4 py-3 bg-white border-b border-slate-200 flex flex-col gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <input
            value={sender}
            onChange={(event) => setSender(event.target.value)}
            placeholder="Your name (optional)"
            className="border border-slate-300 rounded-lg px-2.5 py-1.5 text-sm w-48"
            maxLength={80}
          />
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Note for these frames (optional)"
            className="border border-slate-300 rounded-lg px-2.5 py-1.5 text-sm flex-1 min-w-64"
            maxLength={500}
          />
          <button
            type="button"
            onClick={publishSelected}
            disabled={status !== "connected" || selectedUnique.length === 0}
            className="px-3 py-1.5 rounded-lg text-sm font-bold bg-blue-600 text-white disabled:bg-slate-300 disabled:text-slate-500"
          >
            Share selected ({selectedUnique.length})
          </button>
          <button
            type="button"
            onClick={() => clientRef.current?.clear()}
            disabled={status !== "connected" || items.length === 0}
            className="px-3 py-1.5 rounded-lg text-sm font-semibold border border-rose-300 text-rose-700 bg-rose-50 disabled:opacity-40"
          >
            Clear team list
          </button>
        </div>
        {selectedUnique.length > 0 && (
          <div className="text-[11px] text-slate-500 font-mono truncate">
            Local selection is unchanged: {selectedUnique.join(", ")}
          </div>
        )}
        {error && <div className="text-xs text-rose-700 font-semibold">{error}</div>}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-4">
        {items.length === 0 ? (
          <div className="border border-dashed border-slate-300 bg-white rounded-xl p-10 text-center text-sm text-slate-500">
            Shared shortlist is empty. Select frames in Main search, then return here and publish them.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
            {items.map((item) => (
              <div key={item.frame_id} className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
                <img
                  src={`http://127.0.0.1:6900/api/files/${item.video_id}/${String(item.frame).padStart(6, "0")}`}
                  alt={item.frame_id}
                  className="w-full aspect-video object-cover bg-black"
                  loading="lazy"
                />
                <div className="p-2.5 flex flex-col gap-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs font-extrabold text-slate-900">{item.frame_id}</span>
                    <button
                      type="button"
                      onClick={() => clientRef.current?.removeFrame(item.frame_id)}
                      className="text-[11px] font-bold text-rose-700 hover:underline"
                    >
                      Remove
                    </button>
                  </div>
                  {item.sender && <div className="text-xs text-slate-600">From: <strong>{item.sender}</strong></div>}
                  {item.note && <div className="text-xs text-slate-700 whitespace-pre-wrap">{item.note}</div>}
                  <div className="text-[10px] text-slate-400 font-mono">{item.added_at}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
