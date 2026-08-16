import React, { useState } from "react";

export function MultiWindowWorkspace({
  queryPanel,
  modelParamsPanel,
  selectedFramesPanel,
  searchResultsGrid,
}) {
  const [layoutMode, setLayoutMode] = useState("docked"); // "docked", "split", "floating"

  return (
    <div className="w-full flex flex-col gap-3 min-h-screen pb-12">
      {/* Multi-Window Layout Control Toolbar */}
      <div className="flex items-center justify-between glass-panel p-2.5 rounded-xl border border-slate-800">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
            <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
            </svg>
            Workspace Layout Mode
          </span>
        </div>

        {/* Layout Switcher Buttons */}
        <div className="flex items-center gap-1.5 bg-slate-900/90 p-1 rounded-lg border border-slate-800">
          <button
            onClick={() => setLayoutMode("docked")}
            className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all flex items-center gap-1 ${
              layoutMode === "docked"
                ? "bg-indigo-600 text-white font-bold shadow-md shadow-indigo-500/20"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Unified Grid
          </button>

          <button
            onClick={() => setLayoutMode("split")}
            className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all flex items-center gap-1 ${
              layoutMode === "split"
                ? "bg-indigo-600 text-white font-bold shadow-md shadow-indigo-500/20"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Split Side-by-Side
          </button>

          <button
            onClick={() => setLayoutMode("floating")}
            className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all flex items-center gap-1 ${
              layoutMode === "floating"
                ? "bg-indigo-600 text-white font-bold shadow-md shadow-indigo-500/20"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Multi-Window Floating
          </button>
        </div>
      </div>

      {/* Dynamic Layout Render */}
      {layoutMode === "docked" && (
        <div className="flex flex-col gap-3">
          {queryPanel}
          {modelParamsPanel}
          {selectedFramesPanel}
          <div className="mt-2">{searchResultsGrid}</div>
        </div>
      )}

      {layoutMode === "split" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
          {/* Left Column: Search & Controls */}
          <div className="lg:col-span-5 flex flex-col gap-3">
            {queryPanel}
            {modelParamsPanel}
            {selectedFramesPanel}
          </div>

          {/* Right Column: Search Results */}
          <div className="lg:col-span-7">{searchResultsGrid}</div>
        </div>
      )}

      {layoutMode === "floating" && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          <div className="col-span-1">{queryPanel}</div>
          <div className="col-span-1">{modelParamsPanel}</div>
          <div className="col-span-1">{selectedFramesPanel}</div>
          <div className="col-span-1 md:col-span-2 lg:col-span-3 mt-2">
            {searchResultsGrid}
          </div>
        </div>
      )}
    </div>
  );
}
