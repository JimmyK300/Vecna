#!/usr/bin/env python3
"""Capture only the frozen 31 source anchors for dataset-control #16.

No retrieval input, models, source writes, or whole-video hashes. The default
prints the exact plan. --capture writes a NEW vecna82-temporal-truth-* directory
outside the dataset. Requires ffmpeg/ffprobe and Pillow on the capture host.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

TRUTH_SHA256 = "63f80eb6ff54ef3c623f6ae4926eba404dac8bb5543b86e31f8fa0da842b4c9f"
DATASET_COMMIT = "1f1ad1baef1e1d31817f6c5a12d4d94133611038"
PLAN = [{'query_id': 'p0_q22', 'canonical_query': 'E1: Khoảnh khắc đầu tiên bột được bỏ vào tô măng tây.\nE2: Khoảnh khắc đầu tiên thấy miến măng tây đầu tiên tiếp xúc với dầu trong chảo.\nE3: Khoảnh khắc miếng măng tây đầu tiên rời khỏi chảo dầu.\nE4: Khoảng khắc miếng măng tây cuối cùng rời chảo dầu và nằm hoàn toàn trên dĩa.', 'canonical_query_sha256': '12483e925dc0f1d3ca944fd8a715056a52febcd37534f5b69cdbbd9e53bb4e2f', 'video_id': 'L26_V194', 'video_relative_path': 'videos/L26B/L26_V194.mp4', 'archived_fps': '25/1', 'metadata_path': 'derived/metadata/asr-ocr-text-v1/asr/by-video/L26_V194.json', 'metadata_blob_sha1': 'e3af2718ff73766284a1297372ed0cbeaa6355ec', 'metadata_sha256': '5df1bea989a68707fb2685c8b4a77c827522884b09442c144207c16ed4d1b698', 'anchors': [{'event_index': 1, 'frame': 4707, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}, {'event_index': 2, 'frame': 5139, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}, {'event_index': 3, 'frame': 5427, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}, {'event_index': 4, 'frame': 5865, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}]}, {'query_id': 'p0_q23', 'canonical_query': 'Đoạn video múa lân một con lân màu vàng đen trắng, tìm các sự kiện sau:\nE1: Lân quay vòng trên cột số 4 bằng 2 chân trước rồi tiếp đất. Khoảnh khắc đầu tiên mà lân bắt đầu xoay vòng.\nE2: Khoảnh khắc 4 chân hoàn toàn chạm đất đầu tiên.\nE3: Khoảnh khắc đầu tiên 2 người biểu diễn lân cuối chào ban giám khảo.\nE4: Sau đó lân tiến lại chào một con rồng. Khoảnh khắc đầu tiên con rồng cử động đầu.', 'canonical_query_sha256': 'bcbd4b58239666929025f2b7d42b37936c9a30049dc2891a2615337188b775cb', 'video_id': 'L24_V033', 'video_relative_path': 'videos/L24/L24_V033.mp4', 'archived_fps': '30/1', 'metadata_path': 'derived/metadata/asr-ocr-text-v1/asr/by-video/L24_V033.json', 'metadata_blob_sha1': '96535fc418de58187931c88b19d885e8b80ff344', 'metadata_sha256': '5a7b4f3a401db3e2090d14edccb1199dc4c150d81f99e1ba3c3bcfe9beaf7367', 'anchors': [{'event_index': 1, 'frame': 15945, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}, {'event_index': 2, 'frame': 16006, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}, {'event_index': 3, 'frame': 16354, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}, {'event_index': 4, 'frame': 16901, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}]}, {'query_id': 'p0_q24', 'canonical_query': 'Trong đoạn video nấu ăn một món ăn về nấm, gồm các khoảnh khắc sơ chế:\nE1: Khoảnh khắc đầu tiên thấy cắt nấm.\nE2: Khoảnh khắc đầu tiên cắt củ năng.\nE2: Khoảnh khắc đầu tiên cắt đậu hủ.\nE4: Khoảnh khắc chảo đặt lên bếp, đầu bếp mở lửa và thấy lửa bắt đầu xuất hiện', 'canonical_query_sha256': 'abe95262c85e82a968cc00869eac34f9f3a952ec727a312b9f8eceb7003b786e', 'video_id': 'L26_V072', 'video_relative_path': 'videos/L26A/L26_V072.mp4', 'archived_fps': '25/1', 'metadata_path': 'derived/metadata/asr-ocr-text-v1/asr/by-video/L26_V072.json', 'metadata_blob_sha1': '719ecf484babbe87c5c50644199d3fe529a847a7', 'metadata_sha256': '5a68c99a42bdc040c08b4adbfdc2636cc3f8ad6d45e896ee52fbba121f6523e8', 'anchors': [{'event_index': 1, 'frame': 2466, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}, {'event_index': 2, 'frame': 3133, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}, {'event_index': 3, 'frame': 3420, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}, {'event_index': 4, 'frame': 3800, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}]}, {'query_id': 'p1_q25', 'canonical_query': 'Đoạn video bắt đầu bằng ảnh cận đầu một con lân trắng, mũi đỏ, bên cạnh lá cờ trắng viền đỏ.\nE1 Khoảnh khắc đầu tiên xuất hiện đầy đủ hai con rồng vàng đang xoay vòng.\nE2 Khoảnh khắc đầu tiên con lân hoàn tất cú xoay người trên các thanh trụ (thời điểm đâu tiên các chân của lân đặt trên trụ sau khi xoay).\nE3 Khoảnh khắc đầu tiên dùi chạm vào kẻng đồng múa lân.', 'canonical_query_sha256': 'fabe99ad531f96d61c7bcab0354aa14e3070621a95b4d35d6d053e26b3937a1c', 'video_id': 'L24_V024', 'video_relative_path': 'videos/L24/L24_V024.mp4', 'archived_fps': '30/1', 'metadata_path': 'derived/metadata/asr-ocr-text-v1/asr/by-video/L24_V024.json', 'metadata_blob_sha1': '99ca70c98ccfb75933ebc235ce9cc8e7a04259ee', 'metadata_sha256': '605871b71919a111932a270b81187187a946671cd9bbc5fdd4b774c882e24cd5', 'anchors': [{'event_index': 1, 'frame': 9785, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}, {'event_index': 2, 'frame': 10135, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}, {'event_index': 3, 'frame': 10191, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}]}, {'query_id': 'p2_q29', 'canonical_query': 'Video về một khu vườn cây ăn trái ở miền Tây Nam Bộ. Đây là chuỗi liên tiếp các cảnh quay về 4 loại trái cây trong vườn.\nE1: Cảnh đầu tiên có trái sầu riêng.\nE2: Cảnh đầu tiên có trái măng cụt.\nE3: Cảnh đầu tiên có trái bưởi.\nE4: Cảnh đầu tiên có trái dâu bòn bon.', 'canonical_query_sha256': '32ac6d640f065af07aea8a6986bf9e5b50afebe3ba60d560fafc3c801268f343', 'video_id': 'L27_V011', 'video_relative_path': 'videos/L27/L27_V011.mp4', 'archived_fps': '25/1', 'metadata_path': 'derived/metadata/asr-ocr-text-v1/asr/by-video/L27_V011.json', 'metadata_blob_sha1': '7328f2abfc099b7adbe3e6265202aa606ad2433b', 'metadata_sha256': '81c1b754fe358b709751d2a680714787ff388d00a62aea6ce54de7cf2a1de09d', 'anchors': [{'event_index': 1, 'frame': 3793, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}, {'event_index': 2, 'frame': 3870, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}, {'event_index': 3, 'frame': 4014, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}, {'event_index': 4, 'frame': 4098, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}]}, {'query_id': 'p2_q30', 'canonical_query': '4 cảnh này xảy ra liên tiếp nhau.\nCảnh 1: Hai người phụ nữ cùng nhau dán niêm phong một thùng carton.\nCảnh 2: Các thùng mì tôm và bọc bánh mì được sắp xếp ngay ngắn.\nCảnh 3: Một người đàn ông nhấc thùng mì tôm lên và xếp lên trên chồng thùng mì.\nCảnh 4: Cảnh quay cận cảnh các thùng mì được xếp chồng trên xe tải.', 'canonical_query_sha256': 'd3efa8c87a7071960fd2f705118dcab190268558fc89b97cc0835e65b913d4d3', 'video_id': 'L30_V031', 'video_relative_path': 'videos/L30/L30_V031.mp4', 'archived_fps': '25/1', 'metadata_path': 'derived/metadata/asr-ocr-text-v1/asr/by-video/L30_V031.json', 'metadata_blob_sha1': '2d945da1047072e57728b650bf4a204944112c80', 'metadata_sha256': '65d808f3a6630606564683917416222e322019fdee2bbad8f5694b30073645ca', 'anchors': [{'event_index': 1, 'frame': 2076, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}, {'event_index': 2, 'frame': 2129, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}, {'event_index': 3, 'frame': 2168, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}, {'event_index': 4, 'frame': 2228, 'truth_tier': 'provisional_submission_anchor', 'source_field': 'trake_event_truth'}]}, {'query_id': 'p3_q21', 'canonical_query': 'Một món ăn làm từ tôm và các loại gia vị.\nE1: Khoảnh khắc người đầu bếp bắt đầu trộn hỗn hợp nước xốt, trong nước xốt này có 2 thành phần là nước cam và vỏ cam.\nE2: Khoảnh khắc người đầu bếp bắt đầu cắt bỏ đầu tôm.\nE3: Người đầu bếp cho tôm ra dĩa. Hãy chọn khoảnh khắc con tôm đầu tiên chạm vào dĩa.\nE4: Khoảnh khắc tép cam thứ 4 được xếp lên dĩa khi trang trí món ăn.', 'canonical_query_sha256': 'd81345b4383476336dbd2abcf1843488ca9f65d4af828122231f164890a31331', 'video_id': 'L26_V156', 'video_relative_path': 'videos/L26B/L26_V156.mp4', 'archived_fps': '25/1', 'metadata_path': 'derived/metadata/asr-ocr-text-v1/asr/by-video/L26_V156.json', 'metadata_blob_sha1': 'eb62d56bf2e3aa9e885d8890270d561d6e306f67', 'metadata_sha256': 'accfe561d7889099563e78a4b0b1f6445ca5519e8ba24bc932dcd2582b717a76', 'anchors': [{'event_index': 1, 'frame': 3260, 'truth_tier': 'provisional_source_text_verified_needs_corpus_validation', 'source_field': 'accepted_groups'}, {'event_index': 2, 'frame': 3766, 'truth_tier': 'provisional_source_text_verified_needs_corpus_validation', 'source_field': 'accepted_groups'}, {'event_index': 3, 'frame': 4788, 'truth_tier': 'provisional_source_text_verified_needs_corpus_validation', 'source_field': 'accepted_groups'}, {'event_index': 4, 'frame': 6730, 'truth_tier': 'provisional_source_text_verified_needs_corpus_validation', 'source_field': 'accepted_groups'}]}, {'query_id': 'p3_q34', 'canonical_query': 'Con lân màu đỏ đang biểu diễn trên các cột trụ.\n\nE1: Con lân treo hai chân trước vào phần dưới thân của hai trụ gần cuối (gần trụ cuối cùng cao nhất).\nE2: Con lân đứng thẳng sau khi di chuyển từ cuối dãy trụ về, hai chân đứng trên hai trụ khác nhau và một chân trước co lên.\nE3: Khoảnh khắc con lân hoàn tất động tác ngoảnh mặt theo hướng ngược lại.\nE4: Khoảnh khắc đầu tiên con lân ngậm một thanh trụ.', 'canonical_query_sha256': 'b8db0149b8fdfdc16879dfaf28e980f55177d022a67052f747833ad8288c5949', 'video_id': 'L24_V013', 'video_relative_path': 'videos/L24/L24_V013.mp4', 'archived_fps': '25/1', 'metadata_path': 'derived/metadata/asr-ocr-text-v1/asr/by-video/L24_V013.json', 'metadata_blob_sha1': '5f1592fd77b46a43fc09342505af55601d0ea63a', 'metadata_sha256': '6b460fe9ecd2d3d39071f99972eabdc8d42b04c17d9a7488177803b32fbd9aab', 'anchors': [{'event_index': 1, 'frame': 9900, 'truth_tier': 'provisional_source_text_verified_needs_corpus_validation', 'source_field': 'accepted_groups'}, {'event_index': 2, 'frame': 10218, 'truth_tier': 'provisional_source_text_verified_needs_corpus_validation', 'source_field': 'accepted_groups'}, {'event_index': 3, 'frame': 10330, 'truth_tier': 'provisional_source_text_verified_needs_corpus_validation', 'source_field': 'accepted_groups'}, {'event_index': 4, 'frame': 10576, 'truth_tier': 'provisional_source_text_verified_needs_corpus_validation', 'source_field': 'accepted_groups'}]}]
PLAN_SHA256 = "82b43e196b640a277cfa67e17e127ff9b2f270d13bf7906d8eac1457ad9fbb38"


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
        indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def validate_plan():
    if digest(PLAN) != PLAN_SHA256 or len(PLAN) != 8 or sum(len(q["anchors"]) for q in PLAN) != 31:
        raise ValueError("Frozen 8-query/31-anchor plan identity mismatch")
    for query in PLAN:
        if hashlib.sha256(query["canonical_query"].encode()).hexdigest() != query["canonical_query_sha256"]:
            raise ValueError("Exact canonical query text changed")
        if [event["event_index"] for event in query["anchors"]] != list(range(1, len(query["anchors"]) + 1)):
            raise ValueError("Event ordinals changed")


def sample_frames(anchor, fps):
    # Context seconds plus exact neighboring frames; all include the anchor.
    return sorted({anchor + round(offset * fps) for offset in range(-4, 5)} | {anchor - 1, anchor + 1})


def run(command, seconds):
    result = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=seconds)
    if result.returncode:
        raise RuntimeError("Media subprocess failed: " + result.stderr[-1800:])
    return result


def probe_source(source):
    result = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
        "stream=index,codec_name,width,height,r_frame_rate,avg_frame_rate,time_base,start_time,duration,nb_frames:format=start_time,duration",
        "-of", "json", str(source)], 20)
    value = json.loads(result.stdout)
    if len(value.get("streams", [])) != 1:
        raise ValueError("One unambiguous primary video stream required")
    return value


def observed_pts(stderr, time_base):
    output, integer_ticks = {}, {}
    clocks = dict(re.findall(r"\[showinfo@([a-z0-9_]+)[^\]]*\].*?config in time_base:\s*([0-9/]+)", stderr))
    pattern = r"\[showinfo@([a-z0-9_]+)[^\]]*\].*?\bn:\s*(\d+).*?\bpts:\s*(-?\d+)"
    for label, number, ticks in re.findall(pattern, stderr):
        if label not in clocks or Fraction(clocks[label]) != time_base:
            raise ValueError("Filter/source timebase differs; do not guess timestamp conversion")
        rows = output.setdefault(label, {})
        if int(number) in rows:
            raise ValueError("Duplicate observed source PTS record")
        # pts_time is rounded to six significant digits by FFmpeg, so it is
        # unsuitable for exact source timing at long offsets. Use integer PTS.
        rows[int(number)] = float(int(ticks) * time_base)
        integer_ticks.setdefault(label, {})[int(number)] = int(ticks)
    return output, integer_ticks


def verify_pts(points, frame_ids, fps, time_base, start_time):
    if set(points) != set(range(len(frame_ids))):
        raise ValueError("Decoded frame / observed source PTS coverage is incomplete")
    # Verify observed presentation times, never label n/fps as observed time.
    tolerance = max(0.0001, 2 * float(time_base))
    first_index, first_pts = frame_ids[0], points[0]
    for index, frame in enumerate(frame_ids):
        if abs((points[index] - first_pts) - (frame - first_index) / float(fps)) > tolerance:
            raise ValueError("Variable/uncertain timebase; retain blocker instead of guessing frame/time conversion")
        if abs(points[index] - (float(start_time) + frame / float(fps))) > tolerance:
            raise ValueError("Observed PTS differs from declared start/FPS; source conversion needs review")


def artifact_record(path, out):
    return {"path": path.relative_to(out).as_posix(), "bytes": path.stat().st_size, "sha256": file_sha(path)}


def check_git_export(out):
    repository = next((p for p in out.parents if (p / ".git").exists()), None)
    if repository is None:
        return {"status": "not_inside_git_checkout", "export_guard": "caller must supply a nonignored broker output directory"}
    candidates = [out / name for name in ("evidence-index.json", "p0_q22_filmstrip.jpg", "p0_q22_e1_clip.mp4")]
    result = subprocess.run(["git", "-C", str(repository), "check-ignore", "-v", "--no-index", *map(str, candidates)],
        capture_output=True, text=True, timeout=10)
    if result.returncode not in (0, 1) or result.stdout.strip():
        raise ValueError("Broker would omit output under an ignored path: " + (result.stdout or result.stderr)[-1200:])
    return {"status": "verified_not_ignored", "repository": str(repository), "checked_paths": [str(p) for p in candidates]}


def make_filmstrip(query, samples, files, out):
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    # Pillow's bundled font is a fallback; Windows Arial preserves query accents.
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = ImageFont.truetype(str(font_path), 17) if font_path.is_file() else ImageFont.load_default(size=17)
    small = ImageFont.truetype(str(font_path), 14) if font_path.is_file() else ImageFont.load_default(size=14)
    width, tile_w, tile_h, row_h = 2640, 240, 135, 176
    sheet = Image.new("RGB", (width, 54 + row_h * len(query["anchors"])), "#111827")
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 8), query["query_id"] + " | " + query["video_id"] + " | existing anchors, NOT reviewed truth", font=font, fill="white")
    draw.text((12, 29), "Source PTS and zero-based decoded frames; yellow = anchor, neighbors are one source frame away. Full query: evidence-index.json", font=small, fill="white")
    event_lines = [line for line in query["canonical_query"].splitlines() if re.match(r"^(E\d+|Cảnh\s+\d+)\b", line)]
    for row_index, event in enumerate(query["anchors"]):
        y = 54 + row_index * row_h
        anchor_id = query["query_id"] + ":e" + str(event["event_index"])
        description = event_lines[row_index] if len(event_lines) == len(query["anchors"]) else "See canonical query in evidence index"
        draw.text((8, y), anchor_id + " | frame " + str(event["frame"]) + " | " + description, font=small, fill="white")
        for col, sample in enumerate(samples[anchor_id]):
            x = col * tile_w
            with Image.open(files[sample["source_frame"]]) as image:
                tile = ImageOps.contain(image.convert("RGB"), (tile_w - 2, tile_h))
                sheet.paste(tile, (x, y + 19))
            if sample["source_frame"] == event["frame"]:
                draw.rectangle((x, y + 19, x + tile_w - 2, y + 19 + tile_h), outline="#facc15", width=3)
            label = f"f{sample['source_frame']}  PTS {sample['source_pts_s']:.3f}s"
            draw.text((x + 3, y + 155), label, font=small, fill="white")
    path = out / (query["query_id"] + "_filmstrip.jpg")
    sheet.save(path, quality=77, optimize=True)
    sheet.close()
    return artifact_record(path, out)


def capture_query(query, root, out, timeout):
    qid = query["query_id"]
    source = (root / query["video_relative_path"]).resolve()
    if not source.is_relative_to(root) or source.stem != query["video_id"]:
        raise ValueError("Source video is outside the fixed dataset identity")
    before = source.stat()
    probe = probe_source(source)
    stream = probe["streams"][0]
    fps, avg, time_base = (Fraction(stream[key]) for key in ("r_frame_rate", "avg_frame_rate", "time_base"))
    if fps != Fraction(query["archived_fps"]) or avg != fps or fps <= 0 or fps.denominator != 1:
        raise ValueError("Archived and current FPS disagree or source is not verified integer-CFR")
    start_time = Fraction(stream.get("start_time", "0"))
    all_frames = sorted({frame for event in query["anchors"] for frame in sample_frames(event["frame"], fps)})
    clip_ranges = [(event["frame"] - 5 * int(fps), event["frame"] + 5 * int(fps)) for event in query["anchors"]]
    if min(start for start, end in clip_ranges) < 0 or (stream.get("nb_frames", "N/A").isdigit() and max(end for start, end in clip_ranges) >= int(stream["nb_frames"])):
        raise ValueError("Fixed context crosses source bounds; record access blocker instead of shifting the anchor")
    work = out / (qid + "_frames")
    work.mkdir(exist_ok=False)
    labels = ["still"] + ["c" + str(i + 1) for i in range(len(clip_ranges))]
    filters = ["[0:v:0]split=" + str(len(labels)) + "".join("[" + label + "]" for label in labels)]
    selection = "+".join("eq(n\\," + str(frame) + ")" for frame in all_frames)
    filters.append("[still]select='" + selection + "',scale=512:288:force_original_aspect_ratio=decrease,showinfo@still[stills]")
    for index, (start, end) in enumerate(clip_ranges, 1):
        filters.append(f"[c{index}]trim=start_frame={start}:end_frame={end + 1},scale=512:288:force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2,showinfo@c{index},setpts=PTS-STARTPTS[clip{index}]")
    command = ["ffmpeg", "-nostdin", "-n", "-v", "info", "-threads", "4", "-i", str(source),
        "-filter_complex_threads", "2", "-filter_complex", ";".join(filters),
        "-map", "[stills]", "-frames:v", str(len(all_frames)), "-fps_mode", "vfr", "-q:v", "3", "-an", str(work / "%03d.jpg")]
    for index, (start, end) in enumerate(clip_ranges, 1):
        command += ["-map", f"[clip{index}]", "-frames:v", str(end - start + 1), "-fps_mode", "passthrough",
            "-c:v", "libx264", "-preset", "veryfast", "-b:v", "160k", "-maxrate", "180k", "-bufsize", "360k",
            "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(out / f"{qid}_e{index}_clip.mp4")]
    result = run(command, timeout)
    points, integer_ticks = observed_pts(result.stderr, time_base)
    verify_pts(points.get("still", {}), all_frames, fps, time_base, start_time)
    files = {frame: work / f"{index:03d}.jpg" for index, frame in enumerate(all_frames, 1)}
    if len(list(work.glob("*.jpg"))) != len(files) or any(not path.is_file() for path in files.values()):
        raise ValueError("Exact selected frame image coverage mismatch")
    frame_pts = dict(zip(all_frames, (points["still"][i] for i in range(len(all_frames)))))
    frame_ticks = dict(zip(all_frames, (integer_ticks["still"][i] for i in range(len(all_frames)))))
    samples, anchors = {}, []
    for index, (event, (start, end)) in enumerate(zip(query["anchors"], clip_ranges), 1):
        anchor_id = qid + ":e" + str(event["event_index"])
        frames = sample_frames(event["frame"], fps)
        samples[anchor_id] = [{"source_frame": f, "source_pts_s": frame_pts[f],
            "source_pts_ticks": frame_ticks[f], "source_time_base": str(time_base),
            "is_anchor": f == event["frame"]} for f in frames]
        clip_points = points.get("c" + str(index), {})
        verify_pts(clip_points, list(range(start, end + 1)), fps, time_base, start_time)
        neighbors = []
        for frame in (event["frame"] - 1, event["frame"], event["frame"] + 1):
            path = out / f"{qid}_e{index}_f{frame}.jpg"
            path.write_bytes(files[frame].read_bytes())
            neighbors.append({**artifact_record(path, out), "source_frame": frame, "source_pts_s": frame_pts[frame],
                "source_pts_ticks": frame_ticks[frame], "source_time_base": str(time_base)})
        anchors.append({"evidence_id": anchor_id, "prior_anchor": event, "filmstrip": qid + "_filmstrip.jpg",
            "samples": samples[anchor_id], "adjacent_frames": neighbors,
            "motion_clip": {**artifact_record(out / f"{qid}_e{index}_clip.mp4", out),
                "start_source_frame": start, "end_source_frame": end, "source_frames_inclusive": end - start + 1,
                "start_source_pts_s": clip_points[0], "end_source_pts_s": clip_points[end - start],
                "start_source_pts_ticks": integer_ticks["c" + str(index)][0],
                "end_source_pts_ticks": integer_ticks["c" + str(index)][end - start], "source_time_base": str(time_base),
                "all_source_frames_retained": True, "audio": "omitted; visual-event review", "semantic_review": "PENDING"},
            "review_status": "PENDING_SOURCE_MEDIA_REVIEW", "source_probe_id": qid,
            "context_is_truth_interval": False, "requested_context_s": [-15, 15], "captured_context_s": [-5, 5],
            "coverage_note": "Bounded first pass; does not establish first occurrence outside this window. Expand only with a recorded semantic reason."})
    sheet = make_filmstrip(query, samples, files, out)
    for path in files.values():
        path.unlink()  # Own disposable intermediates only, never source media.
    work.rmdir()
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source file size/mtime changed during capture")
    return {**query, "status": "CAPTURED_NOT_ADJUDICATED", "source_path": str(source),
        "source_stat": {"bytes": before.st_size, "mtime_ns": before.st_mtime_ns}, "source_size_mtime_unchanged": True,
        "source_ffprobe": probe, "source_timebase_check": "all clip frames and filmstrip samples matched observed source PTS",
        "frame_identity_method": "zero-based FFmpeg decoded frame n; no timestamp seek or retrieval ranking", "filmstrip_asset": sheet,
        "capture_command": command, "anchor_evidence": anchors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-seconds", type=float, default=1200)
    args = parser.parse_args()
    validate_plan()
    if not args.capture:
        print(json.dumps({"status": "PLAN_ONLY", "plan_sha256": PLAN_SHA256, "queries": PLAN}, ensure_ascii=False))
        return
    if args.dataset_root is None or args.output_dir is None or not 30 <= args.max_seconds <= 2400:
        parser.error("capture needs dataset-root, new output-dir, and max-seconds within [30,2400]")
    root, out = args.dataset_root.resolve(), args.output_dir.resolve()
    if not root.is_dir() or out.exists() or not out.name.startswith("vecna82-temporal-truth-") or out.is_relative_to(root) or root.is_relative_to(out):
        raise ValueError("Output must be NEW disposable vecna82-temporal-truth-* outside the dataset")
    export_guard = check_git_export(out)
    out.mkdir(parents=True, exist_ok=False)
    manifest = {"schema": "vecna82-temporal-truth-media-v1", "plan_sha256": PLAN_SHA256,
        "truth_sha256": TRUTH_SHA256, "canonical_authority": "JimmyK300/Vecna@f0b0f4707ceab91ba7e266f72fa982dce3ae1c4b:benchmark-results/issue34-current-115/ground_truth_current_115.jsonl",
        "metadata_authority": "JimmyK300/official-dataset-control@" + DATASET_COMMIT,
        "code_sha256": file_sha(Path(__file__)), "started_utc": datetime.now(timezone.utc).isoformat(),
        "full_source_video_hashes": "not_computed", "writes": "new disposable output directory only",
        "retrieval_input_used": False, "source_semantics_adjudicated": False, "queries": [], "status": "IN_PROGRESS"}
    started = time.monotonic()
    for query in PLAN:
        try:
            remaining = args.max_seconds - (time.monotonic() - started)
            if remaining < 20:
                raise TimeoutError("Supervised capture budget exhausted")
            record = capture_query(query, root, out, min(240, remaining))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            record = {**query, "status": "CAPTURE_BLOCKED", "blocker": str(exc)[:1800], "anchor_evidence": []}
        manifest["queries"].append(record)
        save_json(out / "evidence-index.json", manifest)
        print(json.dumps({"query_id": query["query_id"], "status": record["status"], "anchors": len(record["anchor_evidence"])}), flush=True)
    manifest["captured_anchor_count"] = sum(len(q["anchor_evidence"]) for q in manifest["queries"])
    manifest["status"] = "COMPLETE_CAPTURE_PENDING_REVIEW" if manifest["captured_anchor_count"] == 31 else "PARTIAL_CAPTURE_WITH_BLOCKERS"
    manifest["elapsed_s"] = round(time.monotonic() - started, 3)
    manifest["media_bytes"] = sum(p.stat().st_size for p in out.rglob("*") if p.is_file() and p.suffix in (".jpg", ".mp4"))
    manifest["transport"] = {"mode": "binary_git_patch_from_nonignored_output_directory", "export_guard": export_guard,
        "media_artifacts": [artifact_record(p, out) for p in sorted(out.rglob("*")) if p.is_file() and p.suffix in (".jpg", ".mp4")],
        "base64_duplication": False, "receiver_validation": "verify every recovered media SHA256 before inspection"}
    manifest["target_media_budget_bytes"] = 15_000_000
    manifest["within_target_media_budget"] = manifest["media_bytes"] <= 15_000_000
    save_json(out / "evidence-index.json", manifest)
    print(json.dumps({key: manifest[key] for key in ("status", "captured_anchor_count", "elapsed_s", "media_bytes", "within_target_media_budget")}))


if __name__ == "__main__":
    main()
