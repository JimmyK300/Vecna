"""
LLMQueryExpander — Bộ mở rộng câu truy vấn tìm kiếm bằng LLM (Groq / Gemini / OpenAI).

Bắt chước 100% prompt và logic từ dự án caube (D:\\AIC_2026\\caube\\app.py, dòng 456-485):
  - Mô hình: Groq API with openai/gpt-oss-120b (120 tỷ tham số) hoặc llama-3.3-70b-versatile (70 tỷ tham số).
  - Sinh 3 biến thể ngữ nghĩa:
      1. paraphrase: Mở rộng sát nghĩa
      2. role: Nhấn mạnh vai trò / hoạt động của đối tượng
      3. location: Nhấn mạnh nơi chốn / bối cảnh không gian
"""

import json
import os
import re
from functools import lru_cache
from typing import List, Optional

from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger

QUERY_EXPANSION_PROMPT_TEMPLATE = """Bạn là một chuyên gia tối ưu hóa tìm kiếm video chuyên nghiệp. Nhiệm vụ của bạn là mở rộng câu truy vấn gốc của người dùng thành 3 khía cạnh ngữ nghĩa khác nhau: mở rộng theo kiểu sát nghĩa; mở rộng nhấn mạnh vai trò; mở rộng nhấn mạnh nơi chốn. Việc này giúp bộ mã hóa của hệ thống dễ dàng so khớp không gian vector với các keyframes của video.

Ví dụ, câu truy vấn gốc "cô gái nấu ăn" được mở rộng thành:
- Sát nghĩa: "con gái nấu"
- Nhấn mạnh vai trò: "nữ đầu bếp đang chuẩn bị món ăn"
- Nhấn mạnh nơi chốn: "cô gái đang nấu nướng ở nhà bếp"

Câu truy vấn gốc cần mở rộng: "{query}"

Chỉ trả lời bằng một object JSON hợp lệ duy nhất, không kèm giải thích, chú thích hay markdown, đúng định dạng:
{{"paraphrase": "...", "role": "...", "location": "..."}}"""


class LLMQueryExpander:
    """Bộ mở rộng câu truy vấn bằng LLM qua Groq Cloud / OpenAI API / Gemini API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "openai/gpt-oss-120b",
        provider: str = "groq",
    ):
        self._provider = provider.lower()
        self._model_name = model_name
        self._client = None

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

    def expand_query(self, query_text: str) -> List[str]:
        """Sinh 3 biến thể ngữ nghĩa (sát nghĩa / vai trò / nơi chốn) từ query gốc.

        Bắt chước logic từ caube (D:\\AIC_2026\\caube\\app.py, expand_query_with_groq):
          1. Gửi prompt đến LLM yêu cầu JSON response format.
          2. Trích xuất JSON {paraphrase, role, location}.
          3. Trả về danh sách 3 biến thể text.

        Args:
            query_text: Câu truy vấn gốc (ví dụ: "cô gái nấu ăn").

        Returns:
            List[str]: Danh sách các câu biến thể (ví dụ: ["con gái nấu", ...]).
        """
        if not query_text or not query_text.strip() or not self.is_available:
            return []

        prompt = QUERY_EXPANSION_PROMPT_TEMPLATE.format(query=query_text.strip())

        try:
            raw_response = self._generate_text(prompt)
            if not raw_response:
                return []

            # Clean markdown code block wrap (dòng 475 caube)
            raw = re.sub(
                r"^```(json)?|```$", "", raw_response.strip(), flags=re.MULTILINE
            ).strip()
            parsed = json.loads(raw)

            variants = [
                parsed.get("paraphrase", ""),
                parsed.get("role", ""),
                parsed.get("location", ""),
            ]
            variants = [v.strip() for v in variants if v and v.strip()]

            logger.info(f"LLMQueryExpander: '{query_text}' -> {variants}")
            return variants
        except Exception as e:
            logger.error(f"LLMQueryExpander: Error expanding query '{query_text}': {e}")
            return []

    def _generate_text(self, prompt: str) -> str:
        if self._provider == "groq":
            response = self._client.chat.completions.create(
                model=self._model_name,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
        elif self._provider == "gemini":
            response = self._client.generate_content(prompt)
            return response.text
        else:
            response = self._client.chat.completions.create(
                model=self._model_name,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
