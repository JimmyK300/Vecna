"""
LLMQueryExpander — Fast Jina AI-inspired Query Expander with LRU Cache & Multi-Aspect Expansion.
"""

import json
import os
import re
from functools import lru_cache
from typing import Dict, List, Optional

from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger

QUERY_EXPANSION_PROMPT_TEMPLATE = """You are a specialized Query Expansion and Hypothetical Document Embeddings (HyDE) engine for a multimodal video and text retrieval database.

Your objective is to generate search representations that maximize cosine similarity in vision-language models (OpenCLIP, SigLIP, Qwen-VL) and BM25 text match (OCR/ASR) WITHOUT hallucinating ungrounded facts.

### CORE OPERATING PRINCIPLES:
1. STRICT FACTUAL BOUNDARY (ZERO SPECULATION):
   - NEVER introduce unmentioned named entities, specific people, brands, street names, license plates, numbers, or dates unless explicitly stated in the input.
   - If the query is generic (e.g., "tai nạn giao thông"), describe generic visual attributes (e.g., "hai xe máy va chạm trên đường phố đông đúc"), NOT specific fictional locations (e.g., "ngã tư Hàng Xanh").

2. VISUAL GROUNDING FOR HyDE (CLIP/SigLIP ALIGNMENT):
   - Focus strictly on observable visual features: subject, action, camera angle (close-up/wide shot), environment (indoor/outdoor, day/night), lighting, and colors.
   - Keep "en_hyde" within 15–35 words formatted in natural English image caption style (LAION/WebLI style).

3. MULTI-ASPECT OUTPUT SCHEMA:
   - "corrected": Fix spelling and diacritics while STRICTLY PRESERVING the original language. (Do not translate English queries into Vietnamese in this field).
   - "hyde": Vivid visual keyframe description in natural Vietnamese.
   - "en_hyde": High-fidelity English visual caption optimized for English vision-language embeddings (OpenCLIP/SigLIP).
   - "paraphrase": Direct semantic synonyms in the original input language, keeping keyword density high.
   - "search_keywords": 3-5 core visual and textual keywords (separated by commas) for dense/sparse hybrid search.

---

### FEW-SHOT EXAMPLES:

[Example 1 - General Action Query in Vietnamese]
User query: "nguoi di bo sang duong"
Output JSON:
{{
  "corrected": "người đi bộ sang đường",
  "hyde": "cảnh quay góc rộng người đi bộ đang bước qua vạch kẻ đường cho người đi bộ trên đường phố ban ngày",
  "en_hyde": "A wide shot of pedestrians crossing the street on a zebra crosswalk in urban daytime traffic",
  "paraphrase": "người băng qua đường phố",
  "search_keywords": "người đi bộ, sang đường, vạch kẻ đường, pedestrian, crosswalk"
}}

[Example 2 - News / TV Program Query with Specific Entity]
User query: "tin tuc 60s htv hien truong chay nha"
Output JSON:
{{
  "corrected": "tin tức 60s htv hiện trường cháy nhà",
  "hyde": "bản tin truyền hình đưa tin hiện trường vụ hỏa hoạn với khói lửa bốc lên từ ngôi nhà và lực lượng cứu hỏa",
  "en_hyde": "A news report footage showing a house fire scene with thick smoke and firefighters at work",
  "paraphrase": "phóng sự hiện trường hỏa hoạn",
  "search_keywords": "cháy nhà, hỏa hoạn, cứu hỏa, khói lửa, house fire"
}}

[Example 3 - English Input with Typo]
User query: "a polcie car chaisng"
Output JSON:
{{
  "corrected": "a police car chasing",
  "hyde": "cảnh xe cảnh sát bật đèn ưu tiên đang rượt đuổi tốc độ cao trên đường",
  "en_hyde": "A police car with flashing emergency lights in a high-speed vehicle pursuit on a highway",
  "paraphrase": "police vehicle pursuing suspect",
  "search_keywords": "police car, pursuit, chasing, emergency lights, highway"
}}

[Example 4 - Single Word / Short Entity]
User query: "múa lân"
Output JSON:
{{
  "corrected": "múa lân",
  "hyde": "hình ảnh đoàn biểu diễn múa lân sư rồng rực rỡ với trang phục màu đỏ vàng trong lễ hội ngoài trời",
  "en_hyde": "A colorful traditional lion dance performance with red and yellow costumes in a festive outdoor setting",
  "paraphrase": "biểu diễn múa sư tử",
  "search_keywords": "múa lân, lân sư rồng, lion dance, lễ hội, festival"
}}

---

### TASK INPUT:
User query to expand: "{query}"

Respond ONLY with a valid JSON object matching this exact schema:
{{
  "corrected": "...",
  "hyde": "...",
  "en_hyde": "...",
  "paraphrase": "...",
  "search_keywords": "..."
}}"""


class LLMQueryExpander:
    """Bộ mở rộng câu truy vấn bằng LLM qua Groq Cloud / OpenAI API / Gemini API với LRU Cache."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "openai/gpt-oss-120b",
        provider: str = "groq",
        max_tokens: int = 300,
        temperature: float = 0.3,
    ):
        self._provider = provider.lower()
        self._model_name = model_name
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._client = None
        self._cache: Dict[str, Dict[str, str]] = {}

        # Resolve API Key from param, config or env
        resolved_key = (
            api_key
            or GlobalConfig.get("searcher", "llm", "api_key")
            or os.environ.get("GROQ_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )

        if not resolved_key:
            logger.warning(
                "LLMQueryExpander: GROQ_API_KEY not found. Query expansion is disabled."
            )
            return

        try:
            if self._provider == "groq":
                from groq import Groq

                self._client = Groq(api_key=resolved_key)
                logger.info(
                    f"LLMQueryExpander: Initialized Groq client with model '{model_name}'"
                )
            elif self._provider == "gemini":
                import google.generativeai as genai

                genai.configure(api_key=resolved_key)
                self._client = genai.GenerativeModel(model_name)
                logger.info(
                    f"LLMQueryExpander: Initialized Gemini client with model '{model_name}'"
                )
            else:
                from openai import OpenAI

                self._client = OpenAI(api_key=resolved_key)
                logger.info(
                    f"LLMQueryExpander: Initialized OpenAI client with model '{model_name}'"
                )
        except Exception as e:
            logger.error(f"LLMQueryExpander: Failed to initialize LLM client: {e}")
            self._client = None

    @property
    def is_available(self) -> bool:
        return self._client is not None

    def expand_query_detailed(self, query_text: str) -> Dict[str, str]:
        """Sinh 5 biến thể ngữ nghĩa Jina/HyDE (Corrected / HyDE VN / HyDE EN / Paraphrase / Search Keywords) từ query gốc có sử dụng Cache.

        Returns:
            Dict[str, str]: {"corrected": "...", "hyde": "...", "en_hyde": "...", "paraphrase": "...", "search_keywords": "..."}
        """
        if not query_text or not query_text.strip() or not self.is_available:
            return {}

        clean_query = query_text.strip()
        cache_key = clean_query.lower()

        if cache_key in self._cache:
            logger.info(f"LLMQueryExpander: Cache hit for query '{clean_query}' (0ms)")
            return self._cache[cache_key]

        prompt = QUERY_EXPANSION_PROMPT_TEMPLATE.format(query=clean_query)

        try:
            raw_response = self._generate_text(prompt)
            if not raw_response:
                return {}

            raw = re.sub(
                r"^```(json)?|```$", "", raw_response.strip(), flags=re.MULTILINE
            ).strip()
            parsed = json.loads(raw)

            detailed = {
                "corrected": parsed.get("corrected", clean_query).strip(),
                "hyde": parsed.get("hyde", "").strip(),
                "en_hyde": parsed.get("en_hyde", "").strip(),
                "paraphrase": parsed.get("paraphrase", "").strip(),
                "search_keywords": parsed.get("search_keywords", "").strip(),
            }

            if len(self._cache) > 500:
                self._cache.clear()
            self._cache[cache_key] = detailed

            logger.info(f"LLMQueryExpander: Expanded query successfully via Jina pipeline")
            return detailed
        except Exception as e:
            logger.error(f"LLMQueryExpander: Error expanding query '{query_text}': {e}")
            return {}

    def expand_query(self, query_text: str) -> List[str]:
        """Trả về danh sách các biến thể text (Corrected, HyDE VN, HyDE EN, Paraphrase, Search Keywords)."""
        detailed = self.expand_query_detailed(query_text)
        if not detailed:
            return []
        
        variants = [
            detailed.get("corrected", ""),
            detailed.get("hyde", ""),
            detailed.get("en_hyde", ""),
            detailed.get("paraphrase", ""),
            detailed.get("search_keywords", ""),
        ]
        return [v for v in variants if v and v.strip()]

    def _generate_text(self, prompt: str) -> str:
        if self._provider == "groq":
            response = self._client.chat.completions.create(
                model=self._model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=self._temperature,
            )
            return response.choices[0].message.content
        elif self._provider == "gemini":
            response = self._client.generate_content(prompt)
            return response.text
        else:
            response = self._client.chat.completions.create(
                model=self._model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=self._temperature,
            )
            return response.choices[0].message.content
