import React, { useEffect, useState } from "react";

// Values present in workspace2_col's yolo_objects field.
const COLORS = ["black", "blue", "gray", "green", "orange", "red", "unknown", "white", "yellow"];
const OBJECTS = [
  "airplane", "backpack", "bench", "bicycle", "bird", "boat", "bus", "car",
  "chair", "clock", "cow", "dining_table", "dog", "elephant", "fire_hydrant",
  "handbag", "horse", "motorcycle", "parking_meter", "person", "potted_plant",
  "sheep", "skateboard", "stop_sign", "suitcase", "tennis_racket", "traffic_light",
  "train", "truck", "tv", "umbrella",
];
const RELATIONS = [
  ["left_of", "left of"],
  ["right_of", "right of"],
  ["above", "above"],
  ["below", "below"],
  ["near", "near"],
];

const parseKey = (value) => {
  if (!value) return { color1: "", object1: "", relation: "", color2: "", object2: "" };
  const parts = value.split(":");
  const rels = ["left_of", "right_of", "above", "below", "near"];
  if (parts.length === 5) {
    return { color1: parts[0], object1: parts[1], relation: parts[2], color2: parts[3], object2: parts[4] };
  }
  if (parts.length === 3 && rels.includes(parts[1])) {
    return { color1: "", object1: parts[0], relation: parts[1], color2: "", object2: parts[2] };
  }
  if (parts.length === 4) {
    if (rels.includes(parts[2])) {
      return { color1: parts[0], object1: parts[1], relation: parts[2], color2: "", object2: parts[3] };
    }
    if (rels.includes(parts[1])) {
      return { color1: "", object1: parts[0], relation: parts[1], color2: parts[2], object2: parts[3] };
    }
  }
  return { color1: "", object1: "", relation: "", color2: "", object2: "" };
};

const buildKey = (state) => {
  const { color1, object1, relation, color2, object2 } = state;
  if (!object1 || !relation || !object2) return "";
  if (color1 && color2) return `${color1}:${object1}:${relation}:${color2}:${object2}`;
  if (color1 && !color2) return `${color1}:${object1}:${relation}:${object2}`;
  if (!color1 && color2) return `${object1}:${relation}:${color2}:${object2}`;
  return `${object1}:${relation}:${object2}`;
};

export default function YoloRelationFilter({ value = "", onChange, collection }) {
  const isBatch2 = ["workspace2", "testcol2", "2"].includes(collection);
  const [state, setState] = useState(() => parseKey(value));

  useEffect(() => {
    setState(parseKey(value));
  }, [value]);

  useEffect(() => {
    if (!isBatch2) setState(parseKey(""));
  }, [isBatch2]);

  if (!isBatch2) return null;

  const updateField = (field, val) => {
    const next = { ...state, [field]: val };
    setState(next);
    onChange?.(buildKey(next));
  };

  const clear = () => {
    const empty = { color1: "", object1: "", relation: "", color2: "", object2: "" };
    setState(empty);
    onChange?.("");
  };

  const selectClass = "w-full min-w-0 bg-slate-50 border border-gray-300 rounded px-1.5 py-1 text-xs text-gray-900 focus:outline-none focus:border-indigo-500";
  const renderSelect = (label, field, choices, placeholder = "Select...") => (
    <label className="flex flex-col gap-0.5 min-w-0">
      <span className="text-[10px] font-bold text-indigo-700">{label}</span>
      <select
        className={selectClass}
        value={state[field]}
        onChange={(event) => updateField(field, event.target.value)}
      >
        <option value="">{placeholder}</option>
        {choices.map(([key, display]) => <option key={key} value={key}>{display}</option>)}
      </select>
    </label>
  );

  const colorChoices = COLORS.map((item) => [item, item]);
  const objectChoices = OBJECTS.map((item) => [item, item.replaceAll("_", " ")]);
  const relLabel = RELATIONS.find(([k]) => k === state.relation)?.[1] || state.relation;
  const isReady = !!(state.object1 && state.relation && state.object2);
  const preview = isReady
    ? `${state.color1 ? state.color1 + " " : ""}${state.object1.replaceAll("_", " ")} ${relLabel} ${state.color2 ? state.color2 + " " : ""}${state.object2.replaceAll("_", " ")}`
    : "Select Object 1, Relation, and Object 2 to boost results (colors optional)";

  return (
    <div className="w-full lg:w-64 shrink-0 flex flex-col gap-1.5 bg-white border border-indigo-300 p-2 rounded shadow-sm self-start">
      <div className="flex items-center justify-between border-b border-gray-100 pb-1">
        <span className="text-xs font-bold text-gray-800">Object relation boost · Batch 2</span>
        <button type="button" onClick={clear} className="text-[10px] font-bold text-indigo-700 hover:text-indigo-900">Clear</button>
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        {renderSelect("Color 1 (opt)", "color1", colorChoices, "Any color")}
        {renderSelect("Object 1 *", "object1", objectChoices, "Select object...")}
        <div className="col-span-2">{renderSelect("Relation *", "relation", RELATIONS, "Select relation...")}</div>
        {renderSelect("Color 2 (opt)", "color2", colorChoices, "Any color")}
        {renderSelect("Object 2 *", "object2", objectChoices, "Select object...")}
      </div>
      <span className={`text-[10px] break-words ${isReady ? "text-indigo-700 font-semibold" : "text-gray-500 italic"}`}>{preview}</span>
    </div>
  );
}
