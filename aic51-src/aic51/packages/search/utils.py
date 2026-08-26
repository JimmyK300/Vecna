import re
from copy import deepcopy
from functools import lru_cache
from deep_translator import GoogleTranslator

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


@lru_cache(maxsize=1024)
def _raw_translate_vi_to_en(inner_text: str) -> str:
  translated = GoogleTranslator(source="auto", target="en").translate(inner_text)
  if _is_translation_error(translated):
    raise ValueError(f"GoogleTranslator returned error/invalid response: '{translated}'")
  return translated


@lru_cache(maxsize=1024)
def _raw_translate_en_to_vi(inner_text: str) -> str:
  translated = GoogleTranslator(source="auto", target="vi").translate(inner_text)
  if _is_translation_error(translated):
    raise ValueError(f"GoogleTranslator returned error/invalid response: '{translated}'")
  return translated


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
    return text



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
    raw_queries = [q.strip() for q in re.split(r"[\\/]", self._query) if q.strip()]
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

    if len(asr_list):
      features["asr"] = asr_list
      if self._en_to_vi_translate:
        features["asr_translated"] = [translate_en_to_vi(x) for x in asr_list]

    if len(features) == 0:
      return None

    new_q = deepcopy(q)
    new_q["features"] = features
    return new_q
