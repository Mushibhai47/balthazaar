"""
OpenAI (ChatGPT) keyword data collector
Uses GPT to analyze keywords and provide insights
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)


class OpenAICollector(BaseKeywordCollector):
    """Collector for OpenAI ChatGPT keyword insights"""

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.api_key = credentials.get("api_key")
        if not self.api_key:
            raise ValueError("OpenAI API key not found in credentials")

        # Initialize OpenAI client with explicit parameters to avoid proxy issues
        self.client = OpenAI(
            api_key=self.api_key,
            timeout=30.0,
            max_retries=2
        )

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        """
        Collect keyword insights from OpenAI ChatGPT

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

            # Create prompt for GPT
            prompt = self._create_prompt(batch, countries)

            # Call OpenAI API
            response = self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a keyword research expert. Analyze keywords and provide search volume estimates, competition levels, and strategic insights."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,  # Lower temperature for more consistent results
                max_tokens=2000
            )

            # Parse response
            batch_results = self._parse_response(response.choices[0].message.content, batch)
            results.update(batch_results)

        return results

    def _create_prompt(self, keywords: List[str], countries: List[str]) -> str:
        """Create GPT prompt for keyword analysis"""
        countries_str = ", ".join(countries[:5])  # Limit to first 5 countries
        keywords_str = ", ".join(keywords)

        prompt = f"""Analyze these keywords for competitive intelligence purposes in {countries_str}:

Keywords: {keywords_str}

For each keyword, provide:
1. Estimated monthly search volume (number)
2. Competition level (LOW, MEDIUM, HIGH)
3. Estimated CPC in USD (if applicable)
4. Search intent (informational, navigational, transactional, commercial)
5. Brief strategic insight (1 sentence)

Format your response as JSON with this structure:
{{
  "keyword_name": {{
    "search_volume": 10000,
    "competition": "MEDIUM",
    "estimated_cpc": 2.50,
    "intent": "commercial",
    "insight": "Strong commercial intent with moderate competition"
  }}
}}"""

        return prompt

    def _parse_response(self, response_text: str, keywords: List[str]) -> Dict[str, Any]:
        """Parse GPT response into structured data"""
        import json
        import re

        try:
            # Try to extract JSON from response
            # GPT sometimes wraps JSON in markdown code blocks
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
            return parsed_data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI response as JSON: {e}")
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
                    "raw_response": response_text[:200]  # Include snippet for debugging
                }
            return fallback_data

    def validate_credentials(self) -> bool:
        """Validate OpenAI API key"""
        try:
            # Try a minimal API call to validate key
            self.client.models.list()
            return True
        except Exception as e:
            logger.error(f"OpenAI credential validation failed: {e}")
            return False
