import { useLocation, useSubmit } from "react-router-dom";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  limitOptions,
  nprobeOption,
  temporal_k_default,
  ocr_weight_default,
  asr_weight_default,
  max_interval_default,
} from "../resources/options.js";
import { getTargetFeatures } from "../services/search.js";

const DEFAULTS = {
  nprobe: nprobeOption[0],
  limit: limitOptions[0],
  temporal_k: temporal_k_default,
  ocr_weight: ocr_weight_default,
  asr_weight: asr_weight_default,
  max_interval: max_interval_default,
};

export default function SearchParams({ onToggle }) {
  const submit = useSubmit();
  const location = useLocation();
  const [targetFeatures, setTargetFeatures] = useState([]);
  const [values, setValues] = useState(DEFAULTS);
  const [selectedFeatures, setSelectedFeatures] = useState([]);
  const [autoTranslate, setAutoTranslate] = useState(false);
  const [includeVideo, setIncludeVideo] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const pendingSubmit = useRef(null);
  const isSimilar = location.pathname.includes("/similar");

  useEffect(() => {
    getTargetFeatures()
      .then((response) => {
        const features = response.target_features || [];
        setTargetFeatures(Array.isArray(features) ? features : []);
      })
      .catch(() => setTargetFeatures([]));
  }, []);

  useEffect(() => {
    const searchParams = new URLSearchParams(location.search);
    setValues({
      nprobe: searchParams.get("nprobe") || DEFAULTS.nprobe,
      limit: searchParams.get("limit") || DEFAULTS.limit,
      temporal_k: searchParams.get("temporal_k") || DEFAULTS.temporal_k,
      ocr_weight: searchParams.get("ocr_weight") || DEFAULTS.ocr_weight,
      asr_weight: searchParams.get("asr_weight") || DEFAULTS.asr_weight,
      max_interval: searchParams.get("max_interval") || DEFAULTS.max_interval,
    });
    setAutoTranslate(searchParams.get("auto_translate") === "true");
    setIncludeVideo(searchParams.get("include_video") || "");
    setSelectedFeatures(
      (searchParams.get("target_features") || "")
        .split(",")
        .map((feature) => feature.trim())
        .filter(Boolean),
    );
  }, [location.search]);

  const apply = useCallback(
    ({
      nextValues = values,
      nextFeatures = selectedFeatures,
      nextAutoTranslate = autoTranslate,
      nextIncludeVideo = includeVideo,
    } = {}) => {
      const searchParams = new URLSearchParams(location.search);
      const query = searchParams.get("q") || "";
      const id = searchParams.get("id") || "";
      const action = isSimilar ? "/similar" : "/search";
      const payload = isSimilar
        ? {
            ...(id ? { id } : {}),
            limit: nextValues.limit,
            nprobe: nextValues.nprobe,
            ...(nextFeatures.length ? { target_features: nextFeatures.join(",") } : {}),
            offset: 0,
          }
        : {
            ...(query ? { q: query } : {}),
            ...nextValues,
            ...(nextFeatures.length ? { target_features: nextFeatures.join(",") } : {}),
            ...(nextAutoTranslate ? { auto_translate: "true" } : {}),
            ...(nextIncludeVideo.trim() ? { include_video: nextIncludeVideo.trim() } : {}),
            offset: 0,
          };
      submit(
        payload,
        { action },
      );
    },
    [autoTranslate, includeVideo, isSimilar, location, selectedFeatures, submit, values],
  );

  const scheduleApply = (next) => {
    window.clearTimeout(pendingSubmit.current);
    pendingSubmit.current = window.setTimeout(() => apply(next), 250);
  };

  useEffect(() => () => window.clearTimeout(pendingSubmit.current), []);

  const setValue = (name, value) => {
    const nextValues = { ...values, [name]: value };
    setValues(nextValues);
    scheduleApply({ nextValues });
  };

  const setPreset = (ocr, asr) => {
    setValues((current) => ({ ...current, ocr_weight: ocr, asr_weight: asr }));
    scheduleApply({ nextValues: { ...values, ocr_weight: ocr, asr_weight: asr } });
  };

  const setFilter = (setter, key, value) => {
    setter(value);
    scheduleApply({ [key]: value });
  };

  const toggleOpen = () => {
    setIsOpen((open) => !open);
    onToggle?.();
  };

  return (
    <aside className="control-rail" aria-label="Search controls">
      <div className="control-rail-header">
        <div>
          <p className="eyebrow">Search workspace</p>
          <h2>Query controls</h2>
        </div>
        <button
          type="button"
          className="icon-button"
          aria-label={isOpen ? "Collapse query controls" : "Expand query controls"}
          onClick={toggleOpen}
        >
          {isOpen ? "‹" : "›"}
        </button>
      </div>

      {isSimilar ? (
        <>
          <div className="similar-controls-note">
            <p className="eyebrow">Similar mode</p>
            <p>Adjust the image-search limit, probe depth, and target features.</p>
          </div>
          {isOpen && (
            <div className="control-rail-body">
              <section className="control-section">
                <div className="section-heading">
                  <div>
                    <p className="eyebrow">Image retrieval</p>
                    <h3>Search tuning</h3>
                  </div>
                  <span className="status-dot" title="Controls auto-apply" />
                </div>
                <div className="control-grid">
                  <label className="field-label">
                    Candidates
                    <select value={values.limit} onChange={(event) => setValue("limit", event.target.value)}>
                      {limitOptions.map((option) => <option key={option} value={option}>{option}</option>)}
                    </select>
                  </label>
                  <label className="field-label">
                    Probe
                    <select value={values.nprobe} onChange={(event) => setValue("nprobe", event.target.value)}>
                      {nprobeOption.map((option) => <option key={option} value={option}>{option}</option>)}
                    </select>
                  </label>
                </div>
              </section>

              {targetFeatures.length > 0 && (
                <section className="control-section">
                  <div className="section-heading">
                    <div>
                      <p className="eyebrow">Embedding space</p>
                      <h3>Target features</h3>
                    </div>
                  </div>
                  <div className="feature-list">
                    {targetFeatures.map((feature) => (
                      <label key={feature} className="toggle-row">
                        <span>{feature}</span>
                        <input
                          type="checkbox"
                          checked={selectedFeatures.includes(feature)}
                          onChange={(event) => {
                            const nextFeatures = event.target.checked
                              ? [...selectedFeatures, feature]
                              : selectedFeatures.filter((item) => item !== feature);
                            setSelectedFeatures(nextFeatures);
                            scheduleApply({ nextFeatures });
                          }}
                        />
                      </label>
                    ))}
                  </div>
                </section>
              )}
            </div>
          )}
        </>
      ) : isOpen && (
        <div className="control-rail-body">
          <section className="control-section">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Retrieval</p>
                <h3>Search tuning</h3>
              </div>
              <span className="status-dot" title="Controls auto-apply" />
            </div>
            <div className="control-grid">
              <label className="field-label">
                Candidates
                <select value={values.limit} onChange={(event) => setValue("limit", event.target.value)}>
                  {limitOptions.map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
              </label>
              <label className="field-label">
                Probe
                <select value={values.nprobe} onChange={(event) => setValue("nprobe", event.target.value)}>
                  {nprobeOption.map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
              </label>
              <label className="field-label">
                Temporal K
                <input value={values.temporal_k} onChange={(event) => setValue("temporal_k", event.target.value)} />
              </label>
              <label className="field-label">
                Max interval
                <input value={values.max_interval} onChange={(event) => setValue("max_interval", event.target.value)} />
              </label>
            </div>
          </section>

          <section className="control-section">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Scope</p>
                <h3>Video filters</h3>
              </div>
              <span className="section-note">comma separated</span>
            </div>
            <label className="field-label">
              Include video
              <input
                value={includeVideo}
                placeholder="video_001, video_002"
                onChange={(event) => setFilter(setIncludeVideo, "nextIncludeVideo", event.target.value)}
              />
            </label>
            <p className="helper-text">Filters stay outside the query text and are applied automatically.</p>
          </section>

          <section className="control-section">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Fusion</p>
                <h3>Quick presets</h3>
              </div>
            </div>
            <div className="preset-grid">
              <button type="button" onClick={() => setPreset(0, 0)}>CLIP only</button>
              <button type="button" onClick={() => setPreset(1, 0)}>OCR focus</button>
              <button type="button" onClick={() => setPreset(0, 1)}>ASR focus</button>
              <button type="button" onClick={() => setPreset(0.3, 0.2)}>Hybrid</button>
            </div>
            <div className="weight-row">
              <label className="field-label">OCR<input value={values.ocr_weight} onChange={(event) => setValue("ocr_weight", event.target.value)} /></label>
              <label className="field-label">ASR<input value={values.asr_weight} onChange={(event) => setValue("asr_weight", event.target.value)} /></label>
            </div>
            <label className="toggle-row">
              <span>Auto-translate evidence (EN → VI)</span>
              <input
                type="checkbox"
                checked={autoTranslate}
                onChange={(event) => {
                  const nextAutoTranslate = event.target.checked;
                  setAutoTranslate(nextAutoTranslate);
                  scheduleApply({ nextAutoTranslate });
                }}
              />
            </label>
          </section>

          {targetFeatures.length > 0 && (
            <section className="control-section">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Embedding space</p>
                  <h3>Feature sources</h3>
                </div>
              </div>
              <div className="feature-list">
                {targetFeatures.map((feature) => (
                  <label key={feature} className="toggle-row">
                    <span>{feature}</span>
                    <input
                      type="checkbox"
                      checked={selectedFeatures.includes(feature)}
                      onChange={(event) => {
                        const nextFeatures = event.target.checked
                          ? [...selectedFeatures, feature]
                          : selectedFeatures.filter((item) => item !== feature);
                        setSelectedFeatures(nextFeatures);
                        scheduleApply({ nextFeatures });
                      }}
                    />
                  </label>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </aside>
  );
}
