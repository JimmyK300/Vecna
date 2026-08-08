import React, { useState, useEffect } from "react";
import { useLoaderData, Outlet, useSubmit, useLocation } from "react-router-dom";
import VideoProvider from "../components/VideoPlayer.jsx";
import SelectedProvider from "../components/SelectedProvider.jsx";
import AuthProvider from "../components/AuthProvider.jsx";
import AnswerSidebar from "../components/Answer.jsx";
import SearchParams from "../components/SearchParams.jsx";
import { getTargetFeatures } from "../services/search.js";

export async function loader() {
  try {
    const data = await getTargetFeatures();
    return { targetFeatureOptions: data.target_features || [] };
  } catch (error) {
    console.error("Failed to load target features:", error);
    return { targetFeatureOptions: [] };
  }
}

export default function Root() {
  const { targetFeatureOptions } = useLoaderData();
  const submit = useSubmit();
  const location = useLocation();

  // Set Document Title to AIC26
  useEffect(() => {
    document.title = "AIC26";
  }, []);

  // VS Code Style Resizable Vertical Splitter & Collapsible Sidebar Rail
  const [sidebarWidth, setSidebarWidth] = useState(360);
  const [isResizing, setIsResizing] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  const searchParams = new URLSearchParams(location.search);
  const [ocrWeight, setOcrWeight] = useState(parseFloat(searchParams.get("ocr_weight") || "0.5"));
  const [asrWeight, setAsrWeight] = useState(parseFloat(searchParams.get("asr_weight") || "0.0"));
  const [nprobe, setNprobe] = useState(searchParams.get("nprobe") || "32");
  const [limit, setLimit] = useState(searchParams.get("limit") || "20");
  const [temporalK, setTemporalK] = useState(searchParams.get("temporal_k") || "10000");
  const [maxInterval, setMaxInterval] = useState(searchParams.get("max_interval") || "1000");

  const [autoTranslate, setAutoTranslate] = useState(searchParams.get("auto_translate") === "true");
  const [enToViTranslate, setEnToViTranslate] = useState(searchParams.get("en_to_vi_translate") === "true");

  const [selectedFeatures, setSelectedFeatures] = useState(
    searchParams.get("target_features")
      ? searchParams.get("target_features").split(",").filter(Boolean)
      : []
  );

  const handleMouseDown = (e) => {
    e.preventDefault();
    setIsResizing(true);
  };

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isResizing) return;
      const newWidth = Math.min(Math.max(240, e.clientX), 750);
      setSidebarWidth(newWidth);
    };

    const handleMouseUp = () => {
      if (isResizing) {
        setIsResizing(false);
      }
    };

    if (isResizing) {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
    }

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizing]);

  // Keyboard Hotkey 'Tab' to toggle Sidebar Collapse / Expand
  useEffect(() => {
    const handleKeyDown = (e) => {
      const activeEl = document.activeElement;
      const isInInput = activeEl && ["INPUT", "TEXTAREA", "SELECT"].includes(activeEl.tagName);

      if (e.key === "Tab" && !isInInput) {
        e.preventDefault();
        setIsSidebarCollapsed((prev) => !prev);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const triggerParamsChange = (updatedObj = {}) => {
    const currentParams = new URLSearchParams(location.search);
    const q = currentParams.get("q") || "";
    const include_videos = currentParams.get("include_videos") || "";
    const exclude_videos = currentParams.get("exclude_videos") || "";

    const nextAutoTranslate = updatedObj.autoTranslate !== undefined ? updatedObj.autoTranslate : autoTranslate;
    const nextEnToViTranslate = updatedObj.enToViTranslate !== undefined ? updatedObj.enToViTranslate : enToViTranslate;

    const submitData = {
      q,
      auto_translate: nextAutoTranslate ? "true" : "false",
      en_to_vi_translate: nextEnToViTranslate ? "true" : "false",
      include_videos,
      exclude_videos,
      ocr_weight: updatedObj.ocrWeight !== undefined ? updatedObj.ocrWeight : ocrWeight,
      asr_weight: updatedObj.asrWeight !== undefined ? updatedObj.asrWeight : asrWeight,
      nprobe: updatedObj.nprobe !== undefined ? updatedObj.nprobe : nprobe,
      limit: updatedObj.limit !== undefined ? updatedObj.limit : limit,
      temporal_k: updatedObj.temporalK !== undefined ? updatedObj.temporalK : temporalK,
      max_interval: updatedObj.maxInterval !== undefined ? updatedObj.maxInterval : maxInterval,
      target_features: (updatedObj.selectedFeatures !== undefined ? updatedObj.selectedFeatures : selectedFeatures).join(","),
      offset: 0,
    };

    const action = location.pathname.includes("/similar") ? "/similar" : "/search";
    submit(submitData, { action });
  };

  return (
    <AuthProvider>
      <SelectedProvider>
        <VideoProvider>
          <div
            className={`flex flex-row h-screen w-screen overflow-hidden bg-gray-100 text-gray-900 ${
              isResizing ? "cursor-col-resize select-none" : ""
            }`}
          >
            {/* Panel 1: Left Sidebar or VS Code Activity Rail */}
            {isSidebarCollapsed ? (
              /* VS Code Style Collapsed Activity Rail with Quick Model Preset Buttons */
              <div className="w-12 h-full bg-slate-900 text-white flex flex-col items-center py-2 gap-3 shrink-0 shadow-lg select-none border-r border-slate-800 z-30 animate-fadeIn overflow-y-auto">
                {/* AIC26 App Logo */}
                <div
                  onClick={() => setIsSidebarCollapsed(false)}
                  className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center font-extrabold text-[10px] text-white shadow-md cursor-pointer hover:scale-105 transition-transform"
                  title="AIC26 - Click to Expand Sidebar (Tab)"
                >
                  AIC26
                </div>

                {/* Toggle Expand Button */}
                <button
                  onClick={() => setIsSidebarCollapsed(false)}
                  className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
                  title="Expand Sidebar (Tab)"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                  </svg>
                </button>

                {/* Divider */}
                <div className="w-8 h-px bg-slate-800 my-0.5"></div>

                {/* Model Weight Quick Select Buttons (Vertical Rail) */}
                <div className="flex flex-col items-center gap-1.5 w-full px-1">
                  {/* 1. CLIP */}
                  <button
                    onClick={() => {
                      setOcrWeight(0.0);
                      setAsrWeight(0.0);
                      triggerParamsChange({ ocrWeight: 0.0, asrWeight: 0.0 });
                    }}
                    className={`w-9 h-7 rounded-lg text-[10px] font-black tracking-tight transition-all flex items-center justify-center border shadow-sm ${
                      ocrWeight === 0.0 && asrWeight === 0.0
                        ? "bg-blue-600 text-white border-blue-400 ring-2 ring-blue-500/50 scale-105"
                        : "bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700"
                    }`}
                    title="CLIP Model Only (OCR: 0.0, ASR: 0.0)"
                  >
                    CLIP
                  </button>

                  {/* 2. OCR */}
                  <button
                    onClick={() => {
                      setOcrWeight(1.0);
                      setAsrWeight(0.0);
                      triggerParamsChange({ ocrWeight: 1.0, asrWeight: 0.0 });
                    }}
                    className={`w-9 h-7 rounded-lg text-[10px] font-black tracking-tight transition-all flex items-center justify-center border shadow-sm ${
                      ocrWeight === 1.0 && asrWeight === 0.0
                        ? "bg-blue-600 text-white border-blue-400 ring-2 ring-blue-500/50 scale-105"
                        : "bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700"
                    }`}
                    title="OCR Text Only (OCR: 1.0, ASR: 0.0)"
                  >
                    OCR
                  </button>

                  {/* 3. ASR */}
                  <button
                    onClick={() => {
                      setOcrWeight(0.0);
                      setAsrWeight(1.0);
                      triggerParamsChange({ ocrWeight: 0.0, asrWeight: 1.0 });
                    }}
                    className={`w-9 h-7 rounded-lg text-[10px] font-black tracking-tight transition-all flex items-center justify-center border shadow-sm ${
                      ocrWeight === 0.0 && asrWeight === 1.0
                        ? "bg-blue-600 text-white border-blue-400 ring-2 ring-blue-500/50 scale-105"
                        : "bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700"
                    }`}
                    title="ASR Speech Only (OCR: 0.0, ASR: 1.0)"
                  >
                    ASR
                  </button>

                  {/* 4. DEFAULT */}
                  <button
                    onClick={() => {
                      setOcrWeight(0.5);
                      setAsrWeight(0.0);
                      triggerParamsChange({ ocrWeight: 0.5, asrWeight: 0.0 });
                    }}
                    className={`w-9 h-7 rounded-lg text-[10px] font-black tracking-tight transition-all flex items-center justify-center border shadow-sm ${
                      ocrWeight === 0.5 && asrWeight === 0.0
                        ? "bg-gray-600 text-white border-gray-400 ring-2 ring-gray-500/50 scale-105"
                        : "bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700"
                    }`}
                    title="Default Weights (OCR: 0.5, ASR: 0.0)"
                  >
                    DEF
                  </button>

                  {/* 5. HYBRID */}
                  <button
                    onClick={() => {
                      setOcrWeight(0.3);
                      setAsrWeight(0.2);
                      triggerParamsChange({ ocrWeight: 0.3, asrWeight: 0.2 });
                    }}
                    className={`w-9 h-7 rounded-lg text-[10px] font-black tracking-tight transition-all flex items-center justify-center border shadow-sm ${
                      ocrWeight === 0.3 && asrWeight === 0.2
                        ? "bg-purple-600 text-white border-purple-400 ring-2 ring-purple-500/50 scale-105"
                        : "bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700"
                    }`}
                    title="Hybrid Model Weights (OCR: 0.3, ASR: 0.2)"
                  >
                    HYB
                  </button>
                </div>
              </div>
            ) : (
              /* Expanded Resizable Left Sidebar */
              <div
                style={{ width: `${sidebarWidth}px` }}
                className="flex flex-col h-full bg-gray-50 border-r border-gray-300 shadow-sm shrink-0 overflow-y-auto"
              >
                {/* Header with App Name AIC26 & Collapse Button */}
                <div className="px-3 py-2 bg-slate-900 text-white flex items-center justify-between shrink-0 shadow-sm border-b border-slate-800">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse"></span>
                    <span className="font-extrabold text-sm tracking-wider bg-gradient-to-r from-blue-400 to-indigo-300 bg-clip-text text-transparent font-mono">
                      AIC26
                    </span>
                  </div>

                  <button
                    onClick={() => setIsSidebarCollapsed(true)}
                    className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors text-xs font-semibold flex items-center gap-1"
                    title="Collapse Sidebar (Tab)"
                  >
                    <span className="font-mono text-[10px]">Tab ◄</span>
                  </button>
                </div>

                <SearchParams
                  ocrWeight={ocrWeight}
                  setOcrWeight={(w) => {
                    setOcrWeight(w);
                    triggerParamsChange({ ocrWeight: w });
                  }}
                  asrWeight={asrWeight}
                  setAsrWeight={(w) => {
                    setAsrWeight(w);
                    triggerParamsChange({ asrWeight: w });
                  }}
                  nprobe={nprobe}
                  setNprobe={(n) => {
                    setNprobe(n);
                    triggerParamsChange({ nprobe: n });
                  }}
                  limit={limit}
                  setLimit={(l) => {
                    setLimit(l);
                    triggerParamsChange({ limit: l });
                  }}
                  temporalK={temporalK}
                  setTemporalK={(k) => {
                    setTemporalK(k);
                    triggerParamsChange({ temporalK: k });
                  }}
                  maxInterval={maxInterval}
                  setMaxInterval={(i) => {
                    setMaxInterval(i);
                    triggerParamsChange({ maxInterval: i });
                  }}
                  selectedFeatures={selectedFeatures}
                  setSelectedFeatures={(feats) => {
                    setSelectedFeatures(feats);
                    triggerParamsChange({ selectedFeatures: feats });
                  }}
                  autoTranslate={autoTranslate}
                  setAutoTranslate={(val) => {
                    setAutoTranslate(val);
                    triggerParamsChange({ autoTranslate: val });
                  }}
                  enToViTranslate={enToViTranslate}
                  setEnToViTranslate={(val) => {
                    setEnToViTranslate(val);
                    triggerParamsChange({ enToViTranslate: val });
                  }}
                />
                <div className="w-full p-2 border-t border-gray-200">
                  <AnswerSidebar />
                </div>
              </div>
            )}

            {/* VS Code Style Vertical Splitter (Drag Left/Right) */}
            {!isSidebarCollapsed && (
              <div
                onMouseDown={handleMouseDown}
                className={`w-1.5 hover:w-1.5 bg-gray-300 hover:bg-blue-500 cursor-col-resize select-none flex items-center justify-center transition-colors group shrink-0 z-20 ${
                  isResizing ? "bg-blue-600" : ""
                }`}
                title="Drag left / right to resize Sidebar"
              />
            )}

            {/* Main Content Area (Panels 2 & 3 inside) */}
            <div className="flex-1 flex flex-col h-full min-w-0 overflow-hidden p-2">
              <Outlet context={{ targetFeatureOptions, selectedFeatures, triggerParamsChange }} />
            </div>
          </div>
        </VideoProvider>
      </SelectedProvider>
    </AuthProvider>
  );
}
