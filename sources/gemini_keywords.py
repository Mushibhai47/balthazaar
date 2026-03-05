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


class GeminiCollector(BaseKeywordCollector):
    """Collector for Google Gemini keyword insights"""

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.api_key = credentials.get("api_key")
        if not self.api_key:
            raise ValueError("Google Gemini API key not found in credentials")

        # Try newer google.genai package first, fall back to google.generativeai
        try:
            import google.genai as genai
            self.client = genai.Client(api_key=self.api_key)
            self.model_name = "gemini-2.0-flash"
            self.use_new_api = True
            logger.info("Using new google.genai package")
        except (ImportError, Exception):
            import google.generativeai as genai_old
            genai_old.configure(api_key=self.api_key)
            self.model = genai_old.GenerativeModel('gemini-1.5-flash-latest')
            self.use_new_api = False
            logger.info("Using legacy google.generativeai package")

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        """
        Collect keyword insights from Google Gemini

        Args:
            keywords: List of keywords to analyze
            countries: List of countries to target

        Returns:
            Dictionary with keyword insights
        """
        results = {}

        # Process keywords in batches to avoid token limits
        batch_size = 10
        for i in range(0, len(keywords), batch_size):
            batch = keywords[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1} with {len(batch)} keywords")

            # Create prompt for Gemini
            prompt = self._create_prompt(batch, countries)

            # Call Gemini API (handle both old and new API)
            if self.use_new_api:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt
                )
                response_text = response.text
            else:
                response = self.model.generate_content(prompt)
                response_text = response.text

            # Parse response
            batch_results = self._parse_response(response_text, batch)
            results.update(batch_results)

        return results

    def _create_prompt(self, keywords: List[str], countries: List[str]) -> str:
        """Create Gemini prompt for keyword analysis"""
        countries_str = ", ".join(countries[:5])  # Limit to first 5 countries
        keywords_str = ", ".join(keywords)

        prompt = f"""Analyze these keywords for competitive intelligence and market research in {countries_str}:

Keywords: {keywords_str}

For each keyword, provide a comprehensive analysis including:
1. Estimated monthly search volume (realistic number)
2. Competition level (LOW, MEDIUM, or HIGH)
3. Estimated cost-per-click in USD (if applicable for paid advertising)
4. Primary search intent (informational, navigational, transactional, or commercial)
5. Brief strategic recommendation (1 sentence)
6. Trend direction (rising, stable, or declining)

Format your response as valid JSON with this exact structure:
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

        return prompt

    def _parse_response(self, response_text: str, keywords: List[str]) -> Dict[str, Any]:
        """Parse Gemini response into structured data"""
        try:
            # Try to extract JSON from response
            # Gemini sometimes wraps JSON in markdown code blocks
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find JSON object directly
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    json_str = response_text

            parsed_data = json.loads(json_str)

            # Validate and normalize data structure
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
            logger.debug(f"Response text: {response_text}")

            # Fallback: create placeholder data for keywords
            fallback_data = {}
            for keyword in keywords:
                fallback_data[keyword] = {
                    "search_volume": 0,
                    "competition": "UNKNOWN",
                    "estimated_cpc": 0.0,
                    "intent": "unknown",
                    "insight": "Failed to parse AI response",
                    "trend": "unknown",
                    "raw_response": response_text[:200],
                    "source": "google_gemini"
                }
            return fallback_data

    def validate_credentials(self) -> bool:
        """Validate Gemini API key"""
        try:
            if self.use_new_api:
                response = self.client.models.generate_content(
                    model=self.model_name, contents="Hello"
                )
            else:
                response = self.model.generate_content("Hello")
            return bool(response.text)
        except Exception as e:
            logger.error(f"Gemini credential validation failed: {e}")
            return False
