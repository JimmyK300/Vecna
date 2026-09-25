import os
import re
import sqlite3
from copy import deepcopy
from functools import lru_cache
import requests
from deep_translator import GoogleTranslator, MyMemoryTranslator

from aic51.packages.logger import logger
import aic51.packages.constant as global_constant

from . import constants


ERROR_SIGNATURES = (
    "error 500",
    "server error",
    "that’s an error",
    "that's an error",
    "please try again later",
    "that’s all we know",
    "that's all we know",
)


def _is_translation_error(text: str) -> bool:
  if not text or not text.strip():
    return True
  lower = text.lower()
  return any(sig in lower for sig in ERROR_SIGNATURES)


_CACHE_DB_PATH = None


def _get_cache_db_path() -> str:
  global _CACHE_DB_PATH
  if _CACHE_DB_PATH is not None:
    return _CACHE_DB_PATH

  env_path = os.environ.get("AIC51_TRANSLATION_CACHE_DIR")
  if env_path:
    base_dir = env_path
  elif os.path.exists("workspace"):
    base_dir = os.path.join("workspace", "cache")
  else:
    base_dir = os.path.join(".cache", "aic51")

  try:
    os.makedirs(base_dir, exist_ok=True)
    db_path = os.path.join(base_dir, "translations.db")
    with sqlite3.connect(db_path, timeout=5.0) as conn:
      conn.execute(
          "CREATE TABLE IF NOT EXISTS translations ("
          "source_lang TEXT, target_lang TEXT, source_text TEXT, translated_text TEXT, "
          "PRIMARY KEY (source_lang, target_lang, source_text))"
      )
      conn.execute("PRAGMA journal_mode=WAL")
    _CACHE_DB_PATH = db_path
  except Exception:
    _CACHE_DB_PATH = ""
  return _CACHE_DB_PATH


def _get_persistent_cache(source_lang: str, target_lang: str, text: str) -> str | None:
  db_path = _get_cache_db_path()
  if not db_path:
    return None
  try:
    with sqlite3.connect(db_path, timeout=2.0) as conn:
      cur = conn.cursor()
      cur.execute(
          "SELECT translated_text FROM translations WHERE source_lang=? AND target_lang=? AND source_text=?",
          (source_lang, target_lang, text),
      )
      row = cur.fetchone()
      if row and row[0] and not _is_translation_error(row[0]):
        return row[0]
  except Exception:
    pass
  return None


def _save_persistent_cache(source_lang: str, target_lang: str, text: str, translated: str):
  db_path = _get_cache_db_path()
  if not db_path or not translated or _is_translation_error(translated):
    return
  try:
    with sqlite3.connect(db_path, timeout=2.0) as conn:
      conn.execute(
          "INSERT OR REPLACE INTO translations VALUES (?, ?, ?, ?)",
          (source_lang, target_lang, text, translated),
      )
  except Exception:
    pass


def _parse_dict_chrome_response(data) -> str:
  if isinstance(data, str):
    return data.strip()
  if isinstance(data, list):
    if not data:
      return ""
    if isinstance(data[0], str):
      return " ".join(part.strip() for part in data if isinstance(part, str) and part.strip()).strip()
    if isinstance(data[0], list):
      parts = []
      for item in data:
        if isinstance(item, list) and len(item) > 0 and isinstance(item[0], str):
          parts.append(item[0].strip())
        elif isinstance(item, str):
          parts.append(item.strip())
      return " ".join(p for p in parts if p).strip()
  return str(data).strip()


_CHROME_TRANSLATE_HOSTS = (
    "clients5.google.com",
    "translate.googleapis.com",
)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}


def _translate_via_chrome_api(text: str, source: str, target: str) -> str:
  sl = source if source != "auto" else "auto"
  tl = target
  for host in _CHROME_TRANSLATE_HOSTS:
    try:
      url = f"https://{host}/translate_a/t"
      if len(text) < 500:
        resp = requests.get(
            url,
            params={"client": "dict-chrome-ex", "sl": sl, "tl": tl, "q": text},
            headers=_HEADERS,
            timeout=4.0,
        )
      else:
        resp = requests.post(
            url,
            params={"client": "dict-chrome-ex", "sl": sl, "tl": tl},
            data={"q": text},
            headers=_HEADERS,
            timeout=5.0,
        )
      if resp.status_code == 200:
        result = _parse_dict_chrome_response(resp.json())
        if result and not _is_translation_error(result):
          return result
    except Exception:
      continue
  raise RuntimeError("Chrome translate API failed or unreachable")


def _translate_via_mymemory(text: str, source: str, target: str) -> str:
  sl_map = {"vi": "vi-VN", "en": "en-GB", "auto": "vi-VN"}
  tl_map = {"vi": "vi-VN", "en": "en-GB"}
  s = sl_map.get(source, "vi-VN")
  t = tl_map.get(target, "en-GB")
  res = MyMemoryTranslator(source=s, target=t).translate(text)
  if res and not _is_translation_error(res):
    return res.strip()
  raise RuntimeError("MyMemoryTranslator returned empty/invalid response")


def _translate_via_google_scraper(text: str, source: str, target: str) -> str:
  res = GoogleTranslator(source=source, target=target).translate(text)
  if res and not _is_translation_error(res):
    return res.strip()
  raise RuntimeError("GoogleTranslator returned empty/invalid response")


def _translate_with_fallbacks(text: str, source: str, target: str) -> str:
  cached = _get_persistent_cache(source, target, text)
  if cached and not _is_translation_error(cached):
    return cached

  last_err = None
  # Tier 1: Google Chrome Extension API (official browser endpoint, fast JSON, no 429 captcha)
  try:
    translated = _translate_via_chrome_api(text, source, target)
    _save_persistent_cache(source, target, text, translated)
    return translated
  except Exception as e:
    last_err = e

  # Tier 2: MyMemoryTranslator (secondary free online service)
  try:
    translated = _translate_via_mymemory(text, source, target)
    _save_persistent_cache(source, target, text, translated)
    return translated
  except Exception as e:
    last_err = e

  # Tier 3: DeepTranslator GoogleTranslator (fallback web scraper)
  try:
    translated = _translate_via_google_scraper(text, source, target)
    _save_persistent_cache(source, target, text, translated)
    return translated
  except Exception as e:
    last_err = e

  raise ValueError(f"All translation engines failed. Last error: {last_err}")


@lru_cache(maxsize=4096)
def _raw_translate_vi_to_en(inner_text: str) -> str:
  return _translate_with_fallbacks(inner_text, source="vi", target="en")


@lru_cache(maxsize=4096)
def _raw_translate_en_to_vi(inner_text: str) -> str:
  return _translate_with_fallbacks(inner_text, source="en", target="vi")


def translate_vi_to_en_with_status(text: str) -> tuple[str, bool]:
  if not text or not text.strip():
    return text, True
  stripped = text.strip()
  is_quoted = stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= 2
  inner_text = stripped[1:-1].strip() if is_quoted else stripped
  if not inner_text:
    return text, True
  try:
    translated = _raw_translate_vi_to_en(inner_text)
    if translated and translated.strip():
      res = translated.strip()
      if is_quoted:
        res = f'"{res.strip(chr(34))}"'
      try:
        logger.info(f"translate_vi_to_en: '{text}' -> '{res}'")
      except Exception:
        pass
      return res, True
    return text, True
  except Exception as e:
    try:
      logger.error(f"translate_vi_to_en failed for '{text}': {e}")
    except Exception:
      pass
    return text, False


def translate_vi_to_en(text: str) -> str:
  res, _ = translate_vi_to_en_with_status(text)
  return res


def translate_en_to_vi(text: str) -> str:
  if not text or not text.strip():
    return text
  stripped = text.strip()
  is_quoted = stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= 2
  inner_text = stripped[1:-1].strip() if is_quoted else stripped
  if not inner_text:
    return text
  try:
    translated = _raw_translate_en_to_vi(inner_text)
    if translated and translated.strip():
      res = translated.strip()
      if is_quoted:
        res = f'"{res.strip(chr(34))}"'
      try:
        logger.info(f"translate_en_to_vi: '{text}' -> '{res}'")
      except Exception:
        pass
      return res
    return text
  except Exception as e:
    try:
      logger.error(f"translate_en_to_vi failed for '{text}': {e}")
    except Exception:
      pass
COMMON_START_WORDS = {
    "Một", "Hai", "Ba", "Bốn", "Năm", "Sáu", "Bảy", "Tám", "Chín", "Mười",
    "Người", "Những", "Các", "Đoạn", "Hình", "Video", "Cảnh", "Trong", "Khi",
    "Tại", "Có", "Không", "Là", "Và", "Đang", "Được", "Bị", "Cho", "Từ", "Đến",
    "Về", "Với", "Sau", "Trước", "The", "A", "An", "In", "On", "At", "This", "That"
}


def extract_text_entities(text: str) -> list[str]:
    """Semantic Gate: Extract high-confidence text tokens, numbers, codes, and named entities."""
    if not text or not text.strip():
        return []
    entities = []

    # 1. Quoted phrases: "...", '...', “...”, '...'
    for m in re.finditer(r'["\'`“]([^"\'`”]+)["\'`”]', text):
        val = m.group(1).strip()
        if len(val) >= 2:
            entities.append(val)

    # 2. Uppercase codes / callsigns (VTV1, HTV9, Q1, A320, 29A-12345, 51F-9999)
    for m in re.finditer(r'\b(?:[A-Z]{2,}\d*|\d{2,}[A-Z]+[A-Z0-9\-]*|[A-Z]+\d+[A-Z0-9\-]*)\b', text):
        val = m.group().strip()
        if len(val) >= 2 and val not in COMMON_START_WORDS:
            entities.append(val)

    # 3. Significant numeric tokens (e.g. 113, 114, 115, 2024, 2025, 2026, 911)
    for m in re.finditer(r'\b\d{3,}\b', text):
        entities.append(m.group().strip())

    # 4. Capitalized named entities / proper nouns (e.g. Hà Nội, Hồ Chí Minh, VinFast, Samsung)
    words = text.split()
    i = 0
    while i < len(words):
        w = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', words[i])
        if w and w[0].isupper() and len(w) >= 2:
            if i == 0 and w in COMMON_START_WORDS:
                i += 1
                continue
            entity_tokens = [w]
            j = i + 1
            while j < len(words):
                next_w = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', words[j])
                if next_w and next_w[0].isupper() and len(next_w) >= 2:
                    entity_tokens.append(next_w)
                    j += 1
                else:
                    break
            phrase = ' '.join(entity_tokens)
            if phrase not in COMMON_START_WORDS and len(phrase) >= 2:
                entities.append(phrase)
            i = j
        else:
            i += 1

    # Deduplicate while preserving order
    raw_entities = []
    seen = set()
    for e in entities:
        norm = e.strip().lower()
        if norm not in seen and len(norm) >= 2:
            seen.add(norm)
            raw_entities.append(e.strip())

    # Filter out tokens that are strict substrings of longer entities
    result = []
    for i, e in enumerate(raw_entities):
        e_lower = e.lower()
        is_sub = False
        for j, other in enumerate(raw_entities):
            if i != j and e_lower in other.lower() and len(other) > len(e):
                is_sub = True
                break
        if not is_sub:
            result.append(e)

    return result


class Query:

  def __init__(
      self,
      query: str,
      auto_translate: bool = False,
      en_to_vi_translate: bool = False,
      include_videos: str = "",
      exclude_videos: str = "",
  ):
    self._raw_query = deepcopy(query)

    self._query = deepcopy(query)
    self._queries: list = []
    self._include_video_ids = []
    self._exclude_video_ids = []
    self._auto_translate = auto_translate  # VI -> EN for CLIP
    self._en_to_vi_translate = en_to_vi_translate  # EN -> VI for OCR/ASR
    self._init_include_videos = include_videos
    self._init_exclude_videos = exclude_videos
    self._translation_failed = False

    self._parse()

  @property
  def translation_failed(self) -> bool:
    return getattr(self, "_translation_failed", False)


  @property
  def simple(self):
    return len(self._queries) == 0

  @property
  def advance(self):
    return len(self._queries) > 0

  @property
  def temporal(self):
    return len(self._queries) > 1

  @property
  def video_ids(self):
    return self._include_video_ids

  @property
  def include_video_ids(self):
    return self._include_video_ids

  @property
  def exclude_video_ids(self):
    return self._exclude_video_ids

  @property
  def data(self):
    return self._queries

  @property
  def raw(self):
    return self._raw_query

  def _parse(self):
    self._extract_video_ids()
    self._extract_temporal_queries()

    processed_queries = []

    for q in self._queries:
      q = self._parse_one_query(q)
      if q:
        processed_queries.append(q)

    self._queries = processed_queries

  def _extract_video_ids(self):
    include_ids = []
    exclude_ids = []

    if self._init_include_videos:
      for v in re.split(r"[,;\s]+", self._init_include_videos):
        if v.strip():
          include_ids.append(v.strip())

    if self._init_exclude_videos:
      for v in re.split(r"[,;\s]+", self._init_exclude_videos):
        if v.strip():
          exclude_ids.append(v.strip())

    pattern_inc = global_constant.VIDEO_QUERY_PATTERN
    while True:
      video_match = re.search(pattern_inc, self._query, re.IGNORECASE)
      if not video_match:
        break
      video_str = video_match.group().strip("[]")
      video_ids_str = ":".join(video_str.split(":")[1:])
      for item in video_ids_str.split(","):
        if item.strip():
          include_ids.append(item.strip())
      self._query = self._query.replace(video_match.group(), "", 1)

    pattern_exc = getattr(global_constant, "EXCLUDE_VIDEO_QUERY_PATTERN", r"\[(?:exclude_video|!video):[^\]]+\]")
    while True:
      exc_match = re.search(pattern_exc, self._query, re.IGNORECASE)
      if not exc_match:
        break
      exc_str = exc_match.group().strip("[]")
      exc_ids_str = ":".join(exc_str.split(":")[1:])
      for item in exc_ids_str.split(","):
        if item.strip():
          exclude_ids.append(item.strip())
      self._query = self._query.replace(exc_match.group(), "", 1)

    self._include_video_ids = list(dict.fromkeys(include_ids))
    self._exclude_video_ids = list(dict.fromkeys(exclude_ids))

  def _extract_ocr(self, query: str):
    new_query = deepcopy(query)

    pattern = global_constant.OCR_QUERY_PATTERN
    ocr_list = []
    while True:
      ocr_match = re.search(pattern, new_query, re.IGNORECASE)
      if not ocr_match:
        break

      ocr_str = ocr_match.group()
      ocr_str = ocr_str.strip("[]")
      ocr = ":".join(ocr_str.split(":")[1:]).strip()

      if ocr and ocr != '""' and ocr != "''":
        ocr_list.append(ocr.lower())
      new_query = new_query.replace(ocr_match.group(), "", 1)

    return new_query, ocr_list

  def _extract_asr(self, query: str):
    new_query = deepcopy(query)

    pattern = global_constant.ASR_QUERY_PATTERN
    asr_list = []
    while True:
      asr_match = re.search(pattern, new_query, re.IGNORECASE)
      if not asr_match:
        break

      asr_str = asr_match.group()
      asr_str = asr_str.strip("[]")
      asr = ":".join(asr_str.split(":")[1:]).strip()

      if asr and asr != '""' and asr != "''":
        asr_list.append(asr.lower())
      new_query = new_query.replace(asr_match.group(), "", 1)

    return new_query, asr_list

  def _extract_temporal_queries(self):
    # Each non-empty line is one temporal event. Slashes remain ordinary
    # natural-language characters instead of ambiguous delimiters.
    raw_queries = [q.strip() for q in re.split(r"\r?\n", self._query) if q.strip()]
    self._queries = [{"raw": q} for q in raw_queries]

  def _parse_one_query(self, q):
    raw = deepcopy(q["raw"]).strip()

    raw, ocr_list = self._extract_ocr(raw)
    raw, asr_list = self._extract_asr(raw)

    raw = raw.strip()

    features = {}
    if len(raw):
      features["text"] = raw
      if self._auto_translate:
        # VI -> EN translation for CLIP
        translated, success = translate_vi_to_en_with_status(raw)
        features["text_en"] = translated
        if not success:
          self._translation_failed = True
      if self._en_to_vi_translate:
        # EN -> VI translation for OCR/ASR
        features["text_vi"] = translate_en_to_vi(raw)
        features["text_translated"] = features["text_vi"]

    if len(ocr_list):
      features["ocr"] = ocr_list
      if self._en_to_vi_translate:
        features["ocr_translated"] = [translate_en_to_vi(x) for x in ocr_list]
    elif len(raw):
      auto_entities = extract_text_entities(raw)
      if len(auto_entities):
        features["auto_ocr"] = auto_entities

    if len(asr_list):
      features["asr"] = asr_list
      if self._en_to_vi_translate:
        features["asr_translated"] = [translate_en_to_vi(x) for x in asr_list]

    if len(features) == 0:
      return None

    new_q = deepcopy(q)
    new_q["features"] = features
    return new_q
