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

QUERY_EXPANSION_PROMPT_TEMPLATE = """You are a world-class multimodal video search expert and query expansion engine following Jina AI and HyDE (Hypothetical Document Embeddings) principles.

Your task:
1. SPELLING & DIACRITICS CORRECTION: Fix typos and diacritics while STRICTLY PRESERVING the original language of the input query. DO NOT translate English queries into Vietnamese in the "corrected" field!
2. GENERATE 4 MULTI-ASPECT SEARCH REPRESENTATIONS optimized for vector similarity matching (OpenCLIP / SigLIP) and text matching (BM25 OCR/ASR):
   - "corrected": Spell-checked version IN THE SAME LANGUAGE as the input query. If input is English (e.g. "dog", "a dgo"), keep it in English ("dog", "a dog"). If input is Vietnamese (e.g. "con cho"), add proper Vietnamese diacritics ("con chó").
   - "hyde": A vivid, detailed visual scene caption in Vietnamese describing what would be seen in the video keyframe.
   - "en_hyde": A high-quality English visual description translated and optimized specifically for English-pre-trained vision-language models (OpenCLIP / SigLIP).
   - "paraphrase": Semantic rewrite or synonym variation IN THE SAME LANGUAGE as the input query (English for English queries, Vietnamese for Vietnamese queries).

CRITICAL RULES:
1. PRESERVE LANGUAGE FOR CORRECTED & PARAPHRASE: If the user inputs English ("dog"), "corrected" MUST be English ("dog"), NOT Vietnamese ("chó")!
2. ACCURACY FIRST: Fix spelling errors and missing tone marks without translating the language of "corrected".
3. STRICT FACTUAL BOUNDARY: DO NOT introduce unmentioned proper nouns, brand names, or fake details not in the query.
4. ENGLISH OPTIMIZATION: "en_hyde" MUST be natural, descriptive English tailored for CLIP text encoders.

Examples:

[Example 1 - English Input Query]
Input query: "a dgo running on the grass"
Output JSON: {{"corrected": "a dog running on the grass", "hyde": "cảnh một chú chó đang chạy trên bãi cỏ xanh", "en_hyde": "A dog running on green grass in a sunny park", "paraphrase": "a canine running across a lawn"}}

[Example 2 - Single English Word]
Input query: "dog"
Output JSON: {{"corrected": "dog", "hyde": "hình ảnh chú chó trong nhà hoặc ngoài trời", "en_hyde": "A close-up photo of a dog", "paraphrase": "canine"}}

[Example 3 - Vietnamese Typos / Unaccented Input]
Input query: "con cho chay tren co"
Output JSON: {{"corrected": "con chó chạy trên cỏ", "hyde": "cảnh quay một chú chó đang chạy tung tăng trên thảm cỏ xanh trong công viên", "en_hyde": "A vivid photo of a dog running happily on green grass in a sunny park", "paraphrase": "chú chó đang đùa giỡn trên bãi cỏ"}}

User query to expand: "{query}"

Respond with ONLY a valid, single JSON object in this exact format, with no explanations or markdown formatting:
{{"corrected": "...", "hyde": "...", "en_hyde": "...", "paraphrase": "..."}}"""


class LLMQueryExpander:
    """Bộ mở rộng câu truy vấn bằng LLM qua Groq Cloud / OpenAI API / Gemini API với LRU Cache."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "openai/gpt-oss-120b",
        provider: str = "groq",
        max_tokens: int = 150,
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
        """Sinh 4 biến thể ngữ nghĩa Jina AI (Corrected / HyDE VN / HyDE EN / Paraphrase) từ query gốc có sử dụng Cache.

        Returns:
            Dict[str, str]: {"corrected": "...", "hyde": "...", "en_hyde": "...", "paraphrase": "..."}
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
        """Trả về danh sách 4 biến thể text (Corrected, HyDE VN, HyDE EN, Paraphrase)."""
        detailed = self.expand_query_detailed(query_text)
        if not detailed:
            return []
        
        variants = [
            detailed.get("corrected", ""),
            detailed.get("hyde", ""),
            detailed.get("en_hyde", ""),
            detailed.get("paraphrase", ""),
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
