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
const EMPTY = ["", "", "", "", ""];

const parseKey = (value) => {
  const parts = (value || "").split(":");
  return parts.length === 5 ? parts : EMPTY;
};

export default function YoloRelationFilter({ value = "", onChange, collection }) {
  const isBatch2 = ["workspace2", "testcol2", "2"].includes(collection);
  const [parts, setParts] = useState(() => parseKey(value));

  useEffect(() => {
    if (value) setParts(parseKey(value));
  }, [value]);

  useEffect(() => {
    if (!isBatch2) setParts(EMPTY);
  }, [isBatch2]);

  if (!isBatch2) return null;

  const update = (index, selected) => {
    const next = [...parts];
    next[index] = selected;
    setParts(next);
    onChange?.(next.every(Boolean) ? next.join(":") : "");
  };

  const clear = () => {
    setParts(EMPTY);
    onChange?.("");
  };

  const selectClass = "w-full min-w-0 bg-slate-50 border border-gray-300 rounded px-1.5 py-1 text-xs text-gray-900 focus:outline-none focus:border-indigo-500";
  const renderSelect = (label, index, choices) => (
    <label className="flex flex-col gap-0.5 min-w-0">
      <span className="text-[10px] font-bold text-indigo-700">{label}</span>
      <select
        className={selectClass}
        value={parts[index]}
        onChange={(event) => update(index, event.target.value)}
      >
        <option value="">Select...</option>
        {choices.map(([key, display]) => <option key={key} value={key}>{display}</option>)}
      </select>
    </label>
  );

  const colorChoices = COLORS.map((item) => [item, item]);
  const objectChoices = OBJECTS.map((item) => [item, item.replaceAll("_", " ")]);
  const preview = parts.every(Boolean)
    ? `${parts[0]} ${parts[1].replaceAll("_", " ")} ${RELATIONS.find(([key]) => key === parts[2])?.[1] || parts[2]} ${parts[3]} ${parts[4].replaceAll("_", " ")}`
    : "Choose all five fields to boost matching results";

  return (
    <div className="w-full lg:w-64 shrink-0 flex flex-col gap-1.5 bg-white border border-indigo-300 p-2 rounded shadow-sm self-start">
      <div className="flex items-center justify-between border-b border-gray-100 pb-1">
        <span className="text-xs font-bold text-gray-800">Object relation boost · Batch 2</span>
        <button type="button" onClick={clear} className="text-[10px] font-bold text-indigo-700 hover:text-indigo-900">Clear</button>
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        {renderSelect("Color 1", 0, colorChoices)}
        {renderSelect("Object 1", 1, objectChoices)}
        <div className="col-span-2">{renderSelect("Relation", 2, RELATIONS)}</div>
        {renderSelect("Color 2", 3, colorChoices)}
        {renderSelect("Object 2", 4, objectChoices)}
      </div>
      <span className="text-[10px] text-indigo-700 break-words">{preview}</span>
    </div>
  );
}
