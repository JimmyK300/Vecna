import {
  useLoaderData,
  useSubmit,
  useOutletContext,
  useNavigation,
} from "react-router-dom";
import classNames from "classnames";
import { useEffect } from "react";

import { searchSimilar } from "../services/search.js";
import { FrameItem, FrameContainer } from "../components/Frame.jsx";
import { usePlayVideo } from "../components/VideoPlayer.jsx";
import { useSelected } from "../components/SelectedProvider.jsx";

import { 
  limitOptions, 
  nprobeOption,
  temporal_k_default,
  ocr_weight_default,
  asr_weight_default,
  max_interval_default,
} from "../resources/options.js";

export async function loader({ request }) {
  const url = new URL(request.url);
  const searchParams = url.searchParams;

  const id = searchParams.get("id");
  
  if (!id) {
    return {
      query: { id: null },
      params: {},
      offset: 0,
      data: { total: 0, frames: [] },
      error: "No frame ID provided for similarity search",
    };
  }

  const _offset = searchParams.get("offset") || 0;
  const selected = searchParams.get("selected") || undefined;
  const limit = searchParams.get("limit") || limitOptions[0];
  const nprobe = searchParams.get("nprobe") || nprobeOption[0];
  const temporal_k = searchParams.get("temporal_k") || temporal_k_default;
  const ocr_weight = searchParams.get("ocr_weight") || ocr_weight_default;
  const asr_weight = searchParams.get("asr_weight") || asr_weight_default;
  const max_interval = searchParams.get("max_interval") || max_interval_default;
  const target_features = searchParams.get("target_features") || "";

  const { total, frames, params, offset } = await searchSimilar(
    id,
    _offset,
    limit,
    nprobe,
    temporal_k,
    ocr_weight,
    asr_weight,
    max_interval,
    target_features,
  );

  return {
    query: { id },
    params,
    offset,
    data: { total, frames },
  };
}

export default function SearchSimilar() {
  const navigation = useNavigation();
  const { targetFeatureOptions } = useOutletContext();
  const submit = useSubmit();
  const { query, params, offset, data } = useLoaderData();
  const playVideo = usePlayVideo();
  const { clearSelected } = useSelected();

  const { id } = query;
  const { limit, nprobe } = params || { limit: 20, nprobe: 32 };

  const { total, frames } = data || { total: 0, frames: [] };
  const empty = !frames || frames.length === 0;

  useEffect(() => {
    document.title = `Similar to ${id}`;
  }, [id]);

  const goToFirstPage = () => {
    submit({
      ...query,
      ...params,
      offset: 0,
    });
  };

  const goToPreviousPage = () => {
    submit({
      ...query,
      ...params,
      offset: Math.max(parseInt(offset || 0) - parseInt(limit || 20), 0),
    });
  };

  const goToNextPage = () => {
    if (!empty) {
      submit({
        ...query,
        ...params,
        offset: parseInt(offset || 0) + parseInt(limit || 20),
      });
    }
  };

  const handleOnPlay = (frame) => {
    playVideo(frame);
  };

  const handleOnSearchSimilar = (frameKey) => {
    submit({ id: frameKey, ...params }, { action: "/similar" });
  };

  const renderNavBar = (keySuffix = "top") => (
    <div
      key={keySuffix}
      id={`nav-bar-${keySuffix}`}
      className="px-2.5 py-1.5 flex flex-row justify-between items-center text-sm font-bold bg-white border border-gray-200 rounded-xl shrink-0 shadow-sm mb-2"
    >
      <div className="flex items-center gap-2 text-xs text-gray-700 font-mono">
        <span className="bg-purple-100 text-purple-800 font-bold px-2 py-0.5 rounded border border-purple-200">
          Similar to: {id}
        </span>
        <span className="text-gray-300">|</span>
        <span>Total: <strong className="text-blue-700">{total || frames.length}</strong></span>
      </div>

      <div className="flex flex-row items-center gap-1.5">
        {/* Home Button */}
        <button
          onClick={goToFirstPage}
          disabled={parseInt(offset || 0) === 0}
          className={`p-1.5 rounded-lg border flex items-center justify-center transition-all ${
            parseInt(offset || 0) > 0
              ? "bg-white hover:bg-blue-600 hover:text-white border-gray-300 text-gray-700 shadow-sm hover:scale-105 active:scale-95 cursor-pointer"
              : "bg-gray-100 text-gray-300 border-gray-200 cursor-not-allowed"
          }`}
          title="First Page"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l9-9 9 9M5 10v10a1 1 0 001 1h3a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1h3a1 1 0 001-1V10" />
          </svg>
        </button>

        {/* Previous Button */}
        <button
          onClick={goToPreviousPage}
          disabled={parseInt(offset || 0) === 0}
          className={`p-1.5 rounded-lg border flex items-center justify-center transition-all ${
            parseInt(offset || 0) > 0
              ? "bg-white hover:bg-blue-600 hover:text-white border-gray-300 text-gray-700 shadow-sm hover:scale-105 active:scale-95 cursor-pointer"
              : "bg-gray-100 text-gray-300 border-gray-200 cursor-not-allowed"
          }`}
          title="Previous Page"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>

        {/* Page Badge */}
        <div className="px-3 py-1 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg text-xs font-bold text-blue-900 shadow-inner font-mono flex items-center gap-1">
          <span className="text-gray-500 font-normal">Page</span>
          <span className="text-blue-700 font-extrabold text-sm">{Math.floor(parseInt(offset || 0) / parseInt(limit || 20)) + 1}</span>
        </div>

        {/* Next Button */}
        <button
          onClick={goToNextPage}
          disabled={empty}
          className={`p-1.5 rounded-lg border flex items-center justify-center transition-all ${
            !empty
              ? "bg-white hover:bg-blue-600 hover:text-white border-gray-300 text-gray-700 shadow-sm hover:scale-105 active:scale-95 cursor-pointer"
              : "bg-gray-100 text-gray-300 border-gray-200 cursor-not-allowed"
          }`}
          title="Next Page"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex flex-col w-full h-full min-h-0 overflow-y-auto p-2">
      {renderNavBar("top")}

      {empty ? (
        <div className="w-full text-center p-8 bg-white border border-gray-300 rounded text-gray-500 text-sm font-medium">
          No similar keyframes found for ID: {id}
        </div>
      ) : (
        <div
          className={classNames("", {
            "animate-pulse": navigation.state === "loading",
          })}
        >
          <FrameContainer id="result">
            {frames.map((frame) => {
              const frameKey = `${frame.video_id}#${frame.frame_id}`;
              return (
                <FrameItem
                  key={frame.id || frameKey}
                  id={frameKey}
                  video_id={frame.video_id}
                  frame_id={frame.frame_id}
                  thumbnail={`http://127.0.0.1:6900/api/files/${frame.video_id}/${frame.frame_id}`}
                  scores={frame.scores}
                  onPlay={() => handleOnPlay(frame)}
                  onSearchSimilar={() => handleOnSearchSimilar(frameKey)}
                />
              );
            })}
          </FrameContainer>
        </div>
      )}

      {!empty && renderNavBar("bottom")}
    </div>
  );
}
