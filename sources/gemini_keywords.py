"""
Google Gemini keyword data collector
Uses Gemini to analyze keywords and provide insights
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging
import json
import re
import os

logger = logging.getLogger(__name__)

# Models to try in order (most available first)
GEMINI_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro",
    "gemini-1.0-pro",
    "gemini-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-exp",
]


class GeminiCollector(BaseKeywordCollector):
    """Collector for Google Gemini keyword insights"""

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.api_key = credentials.get("api_key")
        if not self.api_key:
            raise ValueError("Google Gemini API key not found in credentials")

        self.client = None
        self.model_name = None
        self.use_new_api = False
        self.legacy_model = None

        # Try newer google.genai package first
        try:
            import google.genai as genai
            self.client = genai.Client(api_key=self.api_key)
            self.use_new_api = True
            logger.info("Using new google.genai package")
        except ImportError:
            pass

        # If new package not available, fall back to legacy
        if not self.use_new_api:
            try:
                import google.generativeai as genai_old
                genai_old.configure(api_key=self.api_key)
                self.legacy_model = genai_old.GenerativeModel('gemini-pro')
                logger.info("Using legacy google.generativeai package")
            except Exception as e:
                raise ValueError(f"Neither google.genai nor google.generativeai available: {e}")

    def _get_working_model(self) -> str:
        """Try models in order, return first one that responds"""
        if self.model_name:
            return self.model_name  # already found a working model

        for model in GEMINI_MODELS:
            try:
                self.client.models.generate_content(model=model, contents="Hi")
                logger.info(f"[gemini] Using model: {model}")
                self.model_name = model
                return model
            except Exception as e:
                if "NOT_FOUND" in str(e) or "404" in str(e):
                    logger.debug(f"[gemini] Model {model} not available, trying next...")
                    continue
                # Other error (auth, quota) - no point trying more models
                raise
        raise ValueError("No working Gemini models found for this API key")

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        results = {}

        batch_size = 10
        for i in range(0, len(keywords), batch_size):
            batch = keywords[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1} with {len(batch)} keywords")

            prompt = self._create_prompt(batch, countries)

            if self.use_new_api:
                model = self._get_working_model()
                response = self.client.models.generate_content(
                    model=model,
                    contents=prompt
                )
                response_text = response.text
            else:
                response = self.legacy_model.generate_content(prompt)
                response_text = response.text

            batch_results = self._parse_response(response_text, batch)
            results.update(batch_results)

        return results

    def _create_prompt(self, keywords: List[str], countries: List[str]) -> str:
        countries_str = ", ".join(countries[:5])
        keywords_str = ", ".join(keywords)

        return f"""Analyze these keywords for competitive intelligence and market research in {countries_str}:

Keywords: {keywords_str}

For each keyword provide:
1. Estimated monthly search volume (realistic number)
2. Competition level (LOW, MEDIUM, or HIGH)
3. Estimated cost-per-click in USD
4. Primary search intent (informational, navigational, transactional, or commercial)
5. Brief strategic recommendation (1 sentence)
6. Trend direction (rising, stable, or declining)

Format your response as valid JSON only:
{{
  "keyword_name": {{
    "search_volume": 10000,
    "competition": "MEDIUM",
    "estimated_cpc": 2.50,
    "intent": "commercial",
    "insight": "Strong commercial intent with moderate competition",
    "trend": "rising"
  }}
}}

Provide ONLY the JSON object, no additional text or markdown formatting."""

    def _parse_response(self, response_text: str, keywords: List[str]) -> Dict[str, Any]:
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                json_str = json_match.group(0) if json_match else response_text

            parsed_data = json.loads(json_str)

            normalized_data = {}
            for keyword, data in parsed_data.items():
                normalized_data[keyword] = {
                    "search_volume": int(data.get("search_volume", 0)),
                    "competition": str(data.get("competition", "UNKNOWN")).upper(),
                    "estimated_cpc": float(data.get("estimated_cpc", 0.0)),
                    "intent": str(data.get("intent", "unknown")).lower(),
                    "insight": str(data.get("insight", "")),
                    "trend": str(data.get("trend", "stable")).lower(),
                    "source": "google_gemini"
                }
            return normalized_data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            return {kw: {
                "search_volume": 0, "competition": "UNKNOWN", "estimated_cpc": 0.0,
                "intent": "unknown", "insight": "Failed to parse AI response",
                "trend": "unknown", "source": "google_gemini"
            } for kw in keywords}

    def validate_credentials(self) -> bool:
        try:
            if self.use_new_api:
                self._get_working_model()
                return True
            else:
                response = self.legacy_model.generate_content("Hello")
                return bool(response.text)
        except Exception as e:
            logger.error(f"Gemini credential validation failed: {e}")
            return False
