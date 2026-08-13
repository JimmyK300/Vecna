import React, { useEffect, useState } from "react";
import { getTargetFeatures } from "../services/search.js";

export default function SearchParams({
  ocrWeight = 0.5,
  setOcrWeight,
  asrWeight = 0.0,
  setAsrWeight,
  setWeights,
  nprobe = 32,
  setNprobe,
  limit = 100,
  setLimit,
  temporalK = 2000,
  setTemporalK,
  maxInterval = 1000,
  setMaxInterval,
  selectedFeatures = [],
  setSelectedFeatures,
  autoTranslate = false,
  setAutoTranslate,
  enToViTranslate = false,
  setEnToViTranslate,
}) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [targetFeatures, setTargetFeatures] = useState([]);

  // Load available target features from backend
  useEffect(() => {
    async function fetchFeatures() {
      try {
        const res = await getTargetFeatures();
        const features = res.target_features || [];
        setTargetFeatures(features);

        // Auto-select CLIP and SIGLIP by default if empty
        if ((!selectedFeatures || selectedFeatures.length === 0) && features.length > 0) {
          const autoDefaults = features.filter((f) => {
            const lower = f.toLowerCase();
            return lower.includes("clip") || lower.includes("siglip");
          });
          const initialSelection = autoDefaults.length > 0 ? autoDefaults : features;
          setSelectedFeatures && setSelectedFeatures(initialSelection);
        }
      } catch (err) {
        console.error("Failed to fetch target features:", err);
      }
    }
    fetchFeatures();
  }, []);

  const handleWeightsChange = (ocr, asr) => {
    if (setWeights) {
      setWeights(ocr, asr);
    } else {
      setOcrWeight && setOcrWeight(ocr);
      setAsrWeight && setAsrWeight(asr);
    }
  };

  const handleCheckboxToggle = (feature) => {
    if (!setSelectedFeatures) return;
    if (selectedFeatures.includes(feature)) {
      setSelectedFeatures(selectedFeatures.filter((f) => f !== feature));
    } else {
      setSelectedFeatures([...selectedFeatures, feature]);
    }
  };

  return (
    <div className="w-full p-3 bg-gray-50 border-b border-gray-200 flex flex-col gap-2.5">
      {/* Header Bar with Collapse Button Only */}
      <div className="flex items-center justify-end pb-1 border-b border-gray-200">
        <button
          type="button"
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="text-xs text-blue-600 hover:text-blue-800 font-semibold flex items-center gap-1"
        >
          {isCollapsed ? "Expand Parameters" : "Collapse Parameters"}
          <span className="text-[10px]">{isCollapsed ? "▼" : "▲"}</span>
        </button>
      </div>

      {/* Quick Weights Buttons Section (Row 1: CLIP, OCR, ASR | Row 2: Default, Hybrid) */}
      <div className="flex flex-col space-y-1.5 bg-white border border-gray-300 rounded-lg p-2 shadow-sm">
        {/* Row 1: CLIP, OCR, ASR */}
        <div className="grid grid-cols-3 gap-1">
          <button
            type="button"
            onClick={() => handleWeightsChange(0.0, 0.0)}
            className={`px-2 py-1 text-xs border rounded font-bold truncate transition-colors ${
              ocrWeight === 0.0 && asrWeight === 0.0
                ? "bg-blue-600 text-white border-blue-600 font-bold"
                : "bg-blue-50 hover:bg-blue-100 border-blue-200 text-blue-700"
            }`}
            title="CLIP model only (OCR: 0.0, ASR: 0.0)"
          >
            CLIP
          </button>

          <button
            type="button"
            onClick={() => handleWeightsChange(1.0, 0.0)}
            className={`px-2 py-1 text-xs border rounded font-bold truncate transition-colors ${
              ocrWeight === 1.0 && asrWeight === 0.0
                ? "bg-blue-600 text-white border-blue-600 font-bold"
                : "bg-blue-50 hover:bg-blue-100 border-blue-200 text-blue-700"
            }`}
            title="OCR text only (OCR: 1.0, ASR: 0.0)"
          >
            OCR
          </button>

          <button
            type="button"
            onClick={() => handleWeightsChange(0.0, 1.0)}
            className={`px-2 py-1 text-xs border rounded font-bold truncate transition-colors ${
              ocrWeight === 0.0 && asrWeight === 1.0
                ? "bg-blue-600 text-white border-blue-600 font-bold"
                : "bg-blue-50 hover:bg-blue-100 border-blue-200 text-blue-700"
            }`}
            title="ASR speech only (OCR: 0.0, ASR: 1.0)"
          >
            ASR
          </button>
        </div>

        {/* Row 2: Default, Hybrid */}
        <div className="grid grid-cols-2 gap-1">
          <button
            type="button"
            onClick={() => handleWeightsChange(0.5, 0.0)}
            className={`px-2 py-1 text-xs border rounded font-bold truncate transition-colors ${
              ocrWeight === 0.5 && asrWeight === 0.0
                ? "bg-gray-700 text-white border-gray-700"
                : "bg-gray-100 hover:bg-gray-200 border-gray-300 text-gray-700"
            }`}
            title="Default model weights (OCR: 0.5, ASR: 0.0)"
          >
            Default
          </button>

          <button
            type="button"
            onClick={() => handleWeightsChange(0.3, 0.2)}
            className={`px-2 py-1 text-xs border rounded font-bold truncate transition-all shadow-sm ${
              ocrWeight === 0.3 && asrWeight === 0.2
                ? "bg-purple-600 text-white border-purple-600"
                : "bg-purple-50 hover:bg-purple-100 border-purple-200 text-purple-700"
            }`}
            title="Hybrid model weights (OCR: 0.3, ASR: 0.2)"
          >
            Hybrid
          </button>
        </div>

        {/* Current Weight Values Indicator */}
        <div className="flex justify-between items-center text-[11px] pt-1 text-gray-600 border-t border-gray-100 font-mono truncate">
          <span className="truncate">OCR Weight: <strong className="text-blue-700">{ocrWeight}</strong></span>
          <span className="truncate">ASR Weight: <strong className="text-purple-700">{asrWeight}</strong></span>
        </div>
      </div>

      {/* Collapsible Parameters Container (Includes Translation Toggles & Model Constants) */}
      {!isCollapsed && (
        <div className="flex flex-col gap-2 pt-1 border-t border-gray-200 animate-fadeIn">
          {/* Translation Settings Section (Inside Collapsible Area) */}
          <div className="flex flex-col space-y-1.5 bg-white border border-gray-300 rounded-lg p-2 shadow-sm">
            <span className="text-xs font-bold text-gray-700">Translation Toggles</span>
            <div className="grid grid-cols-2 gap-1.5">
              {/* VI -> EN CLIP Translation Toggle */}
              <button
                type="button"
                onClick={() => setAutoTranslate && setAutoTranslate(!autoTranslate)}
                className={`px-2 py-1 text-xs border rounded-md font-bold transition-all shadow-sm flex items-center justify-center gap-1 ${
                  autoTranslate
                    ? "bg-blue-600 text-white border-blue-600"
                    : "bg-blue-50 hover:bg-blue-100 border-blue-200 text-blue-700"
                }`}
                title="Translate Vietnamese query to English for CLIP model"
              >
                VI ➔ EN CLIP
              </button>

              {/* EN -> VI OCR/ASR Translation Toggle */}
              <button
                type="button"
                onClick={() => setEnToViTranslate && setEnToViTranslate(!enToViTranslate)}
                className={`px-2 py-1 text-xs border rounded-md font-bold transition-all shadow-sm flex items-center justify-center gap-1 ${
                  enToViTranslate
                    ? "bg-amber-600 text-white border-amber-600"
                    : "bg-amber-50 hover:bg-amber-100 border-amber-200 text-amber-800"
                }`}
                title="Translate English OCR/ASR text to Vietnamese"
              >
                EN ➔ VI OCR/ASR
              </button>
            </div>
          </div>

          {/* Target Feature Models Selector */}
          <div className="flex flex-col bg-white border border-gray-300 rounded-lg p-2 gap-1.5 shadow-sm">
            <div className="flex items-center justify-between">
              <label className="font-bold text-xs text-gray-800">
                Target Feature Models
              </label>
              <span className="text-[10px] bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded font-semibold">
                Auto-Selected CLIP/SIGLIP
              </span>
            </div>

            {targetFeatures.length === 0 ? (
              <div className="text-xs text-gray-400 italic">Loading feature models...</div>
            ) : (
              <div className="max-h-36 overflow-y-auto grid grid-cols-2 gap-1.5 pt-1">
                {targetFeatures.map((item) => {
                  const isChecked = selectedFeatures.includes(item);
                  const lower = item.toLowerCase();
                  let displayName = item;
                  if (lower.includes("siglip")) displayName = "SigLIP";
                  else if (lower.includes("clip")) displayName = "CLIP";

                  return (
                    <label key={item} className="flex items-center gap-1.5 text-xs text-gray-700 cursor-pointer hover:text-gray-900">
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => handleCheckboxToggle(item)}
                        className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      />
                      <span className="truncate text-xs font-bold">{displayName}</span>
                    </label>
                  );
                })}
              </div>
            )}
          </div>

          {/* Model Constants Grid Inputs */}
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="flex items-center bg-white border border-gray-300 rounded p-1 gap-1">
              <label className="font-bold text-[11px] text-gray-600">nprobe:</label>
              <select
                value={nprobe}
                onChange={(e) => setNprobe && setNprobe(e.target.value)}
                className="focus:outline-none text-xs flex-1 bg-transparent"
              >
                {["16", "32", "64", "128"].map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-center bg-white border border-gray-300 rounded p-1 gap-1">
              <label className="font-bold text-[11px] text-gray-600">limit:</label>
              <select
                value={limit}
                onChange={(e) => setLimit && setLimit(e.target.value)}
                className="focus:outline-none text-xs flex-1 bg-transparent"
              >
                {["10", "20", "50", "100", "200"].map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-center bg-white border border-gray-300 rounded p-1 gap-1">
              <label className="font-bold text-[11px] text-gray-600">temporal_k:</label>
              <input
                value={temporalK}
                onChange={(e) => setTemporalK && setTemporalK(e.target.value)}
                className="focus:outline-none text-xs w-full bg-transparent"
              />
            </div>

            <div className="flex items-center bg-white border border-gray-300 rounded p-1 gap-1">
              <label className="font-bold text-[11px] text-gray-600">max_interval:</label>
              <input
                value={maxInterval}
                onChange={(e) => setMaxInterval && setMaxInterval(e.target.value)}
                className="focus:outline-none text-xs w-full bg-transparent"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}