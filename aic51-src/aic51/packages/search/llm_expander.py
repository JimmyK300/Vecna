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

QUERY_EXPANSION_PROMPT_TEMPLATE = """You are a professional video search query optimization and spelling correction expert following Jina AI principles.
Your task is to:
1. AUTOMATICALLY FIX ANY TYPOS, UNACCENTED VIETNAMESE, OR SPELLING MISTAKES in the user's input query (e.g. "con cho" or "con chos" -> "con chó", "nguoi nau an" -> "người nấu ăn").
2. Expand the spell-checked query into 3 visual search representations for CLIP/SigLIP vector matching:
   - "corrected": The spell-checked, properly accented standard version of the user query.
   - "hyde": A vivid, hypothetical visual scene/caption description matching video keyframes for CLIP/SigLIP.
   - "paraphrase": A direct semantic rewrite or synonym variation.

CRITICAL INSTRUCTIONS:
1. SPELLING & DIACRITIC CORRECTION: Fix missing Vietnamese tone marks/accents and typos first.
2. STRICT FACTUAL BOUNDARY: DO NOT introduce unmentioned locations, proper nouns, or fake details not in the query.
3. LANGUAGE PRESERVATION: Always preserve and match the SAME language as the input query for all output variations.

Examples:

[Example 1 - Vietnamese Typos / Unaccented Input]
Input query: "con cho"
Output JSON: {{"corrected": "con chó", "hyde": "bức ảnh một con chó đang đứng hoặc chạy trên thảm cỏ trong công viên", "paraphrase": "chú chó"}}

[Example 2 - Vietnamese Input]
Input query: "cô gái nấu ăn"
Output JSON: {{"corrected": "cô gái nấu ăn", "hyde": "cô gái đang đứng trong bếp làm món ăn nóng hổi", "paraphrase": "con gái đang nấu nướng"}}

User query to expand: "{query}"

Respond with ONLY a valid, single JSON object, with no explanations, notes, or markdown formatting, in the following exact format:
{{"corrected": "...", "hyde": "...", "paraphrase": "..."}}"""


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
        """Sinh 3 biến thể ngữ nghĩa Jina AI (Corrected / HyDE / Paraphrase) từ query gốc có sử dụng Cache.

        Returns:
            Dict[str, str]: {"corrected": "...", "hyde": "...", "paraphrase": "..."}
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
        """Trả về danh sách 3 biến thể text (Corrected, HyDE, Paraphrase)."""
        detailed = self.expand_query_detailed(query_text)
        if not detailed:
            return []
        
        variants = [
            detailed.get("corrected", ""),
            detailed.get("hyde", ""),
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
