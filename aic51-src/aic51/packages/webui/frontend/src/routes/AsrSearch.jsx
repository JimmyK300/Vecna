import React, { useState } from "react";
import axios from "axios";
import { FrameItem } from "../components/Frame.jsx";
import { usePlayVideo } from "../components/VideoPlayer.jsx";

const PORT = (typeof import.meta !== "undefined" && import.meta.env && import.meta.env.VITE_PORT) || 6900;

export default function AsrSearch() {
  const [query, setQuery] = useState("");
  const [sentenceLevel, setSentenceLevel] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState({ frames: [], total: 0, operator_mode: "raw" });
  const playVideo = usePlayVideo();

  const runSearch = async (event) => {
    if (event) event.preventDefault();
    const q = query.trim();
    if (!q) {
      setData({ frames: [], total: 0, operator_mode: sentenceLevel ? "sentence" : "raw" });
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await axios.get(`http://127.0.0.1:${PORT}/api/search_asr_operator`, {
        params: {
          q,
          sentence_level: sentenceLevel,
          offset: 0,
          limit: 20,
          nprobe: 32,
        },
      });
      setData(response.data || { frames: [], total: 0 });
    } catch (err) {
      setError(err?.response?.data?.message || err.message || "ASR search failed");
      setData({ frames: [], total: 0, operator_mode: sentenceLevel ? "sentence" : "raw" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col w-full h-full min-h-0 overflow-y-auto p-3 gap-3 bg-gray-50">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-lg font-extrabold text-slate-900">ASR Operator Search</h1>
          <p className="text-xs text-slate-600">
            Pure existing ASR BM25. Sentence grouping is optional and does not affect normal multimodal search.
          </p>
        </div>
        <a href="/search" className="text-xs font-bold px-3 py-1.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-100">
          ← Main search
        </a>
      </div>

      <form onSubmit={runSearch} className="bg-white border border-slate-200 rounded-xl p-3 shadow-sm flex flex-col gap-2">
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={3}
          placeholder="Search spoken/transcribed content…"
          className="w-full border border-slate-300 rounded-lg p-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <label className="flex items-center gap-2 text-sm font-semibold text-slate-700 select-none">
            <input
              type="checkbox"
              checked={sentenceLevel}
              onChange={(e) => setSentenceLevel(e.target.checked)}
            />
            Group identical same-video ASR sentences
          </label>
          <div className="flex items-center gap-2">
            <span className={`text-[11px] font-bold px-2 py-1 rounded-full ${sentenceLevel ? "bg-indigo-100 text-indigo-800" : "bg-slate-100 text-slate-700"}`}>
              {sentenceLevel ? "Sentence grouped" : "Raw frames (default)"}
            </span>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-slate-400 text-white text-sm font-bold"
            >
              {loading ? "Searching…" : "Search ASR"}
            </button>
          </div>
        </div>
      </form>

      {error && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-2">{error}</div>}

      <div className="flex items-center gap-2 text-xs text-slate-600 font-mono">
        <span>Mode: <strong>{data.operator_mode || (sentenceLevel ? "sentence" : "raw")}</strong></span>
        <span>•</span>
        <span>Total top-level results: <strong>{data.total || 0}</strong></span>
        <span>•</span>
        <span>Showing: <strong>{(data.frames || []).length}</strong></span>
      </div>

      {(data.frames || []).length === 0 ? (
        <div className="p-8 text-center text-sm text-slate-500 bg-white border border-slate-200 rounded-xl">
          {loading ? "Searching ASR…" : "No ASR results yet."}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
          {data.frames.map((frame, index) => {
            const group = frame.sentence_group;
            const representative = frame.frame_id;
            const score = frame.scores?.final ?? 0;
            return (
              <div key={`${frame.id}-${index}`} className="bg-white border border-slate-200 rounded-xl p-2 shadow-sm flex flex-col gap-2">
                <FrameItem
                  id={frame.id}
                  video_id={frame.video_id}
                  frame_id={representative}
                  thumbnail={`http://127.0.0.1:6900/api/files/${frame.video_id}/${representative}`}
                  scores={frame.scores}
                  ocr={frame.ocr}
                  onPlay={() => playVideo({ video_id: frame.video_id, frame_id: representative }, representative)}
                  onSearchSimilar={() => {}}
                />
                <div className="text-xs text-slate-700 flex flex-col gap-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold">ASR score {Number(score).toFixed(4)}</span>
                    {group && (
                      <span className="font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-full">
                        {group.member_count} frames in sentence group
                      </span>
                    )}
                  </div>
                  <div className="bg-slate-50 border border-slate-100 rounded p-2 whitespace-pre-wrap break-words">
                    {group?.asr_text || frame.asr || "(empty ASR text)"}
                  </div>
                  {group && (
                    <div className="text-[11px] text-slate-500 font-mono break-all">
                      Frames: {group.member_frames.map((m) => m.frame).join(", ")}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
