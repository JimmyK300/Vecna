/* eslint-disable react/prop-types */

const ROAD_OPTIONS = [
  ["", "Mọi loại đường"],
  ["three_way", "Ngã ba"],
  ["four_way", "Ngã tư"],
  ["roundabout", "Vòng xoay / bùng binh"],
  ["bridge", "Chân cầu / hầm chui"],
];

const LIGHTING_OPTIONS = [
  ["", "Mọi thời điểm"],
  ["day", "Trời sáng (ước tính)"],
  ["night", "Trời tối (ước tính)"],
  ["unknown", "Chưa xác định"],
];

export default function CameraSceneFilter({ collection, roadType = "", lighting = "", onChange }) {
  if (!(["workspace2", "testcol2", "2"].includes(collection))) return null;

  const selectClass = "w-full min-w-0 bg-slate-50 border border-gray-300 rounded px-2 py-1 text-xs text-gray-900 focus:outline-none focus:border-teal-500";
  return (
    <div className="w-full lg:w-48 shrink-0 flex flex-col gap-2 bg-white border border-teal-300 p-2 rounded shadow-sm self-start">
      <div className="flex items-center justify-between border-b border-gray-100 pb-1">
        <span className="text-xs font-bold text-gray-800">Bối cảnh camera · Batch 2</span>
        <button type="button" onClick={() => onChange?.("", "")} className="text-[10px] font-bold text-teal-700 hover:text-teal-900">Xóa</button>
      </div>
      <label className="flex flex-col gap-0.5">
        <span className="text-[10px] font-bold text-teal-700">Loại giao lộ</span>
        <select className={selectClass} value={roadType} onChange={(event) => onChange?.(event.target.value, lighting)}>
          {ROAD_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-0.5">
        <span className="text-[10px] font-bold text-teal-700">Ánh sáng</span>
        <select className={selectClass} value={lighting} onChange={(event) => onChange?.(roadType, event.target.value)}>
          {LIGHTING_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <span className="text-[10px] leading-tight text-slate-500">Sáng/tối suy từ giờ OCR của video; giờ đọc sai được xếp chưa xác định.</span>
    </div>
  );
}
