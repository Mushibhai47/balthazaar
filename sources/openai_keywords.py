"""
OpenAI (ChatGPT) keyword data collector
Uses GPT to analyze keywords and provide insights
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging

import httpx
from openai import OpenAI

logger = logging.getLogger(__name__)


class OpenAICollector(BaseKeywordCollector):
    """Collector for OpenAI ChatGPT keyword insights"""

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.api_key = credentials.get("api_key")
        if not self.api_key:
            raise ValueError("OpenAI API key not found in credentials")

        # Use explicit httpx client to bypass Replit proxy injection
        self.client = OpenAI(
            api_key=self.api_key,
            http_client=httpx.Client(trust_env=False),
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
                model="gpt-4o-mini",
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

        # Generate top 10 AI prompts for the topic
        try:
            ai_prompts = self._generate_ai_prompts(keywords, countries)
            if ai_prompts:
                results['_ai_prompts'] = ai_prompts
        except Exception as e:
            logger.warning(f"AI prompts generation failed: {e}")

        return results

    def _create_prompt(self, keywords: List[str], countries: List[str]) -> str:
        """Create GPT prompt for keyword analysis"""
        countries_str = ", ".join(countries[:5])  # Limit to first 5 countries
        keywords_str = ", ".join(keywords)

        prompt = f"""Analyze these keywords for competitive intelligence purposes in {countries_str}:

Keywords: {keywords_str}

For each keyword, provide:
1. Estimated monthly search volume for the current period (number)
2. Estimated average monthly search volume over the last 6 identical periods (number) — e.g. if reporting fortnightly, average over last 6 fortnights
3. Trend: is search volume rising, declining, or stable? Include estimated % change vs previous period
4. Competition level (LOW, MEDIUM, HIGH)
5. Estimated CPC in USD (if applicable)
6. Search intent (informational, navigational, transactional, commercial)
7. Brief strategic insight (1 sentence)

Format your response as JSON with this structure:
{{
  "keyword_name": {{
    "search_volume": 10000,
    "avg_volume_6p": 9500,
    "trend": "rising",
    "trend_pct": 12.5,
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

    def _generate_ai_prompts(self, keywords: List[str], countries: List[str]) -> List[Dict[str, Any]]:
        """Generate top 10 natural language AI search prompts related to the tracked keywords"""
        import json, re
        topic = ", ".join(keywords[:5])
        country = countries[0] if countries else "the target market"

        prompt = f"""Based on these keywords related to a business topic: {topic}

Generate the top 10 natural language questions or prompts that people would type into ChatGPT or an AI assistant when researching this topic in {country}.

These should be realistic, conversational queries — not just keyword phrases.

For each prompt, estimate:
- Monthly AI search volume (how many times per month people ask this type of question)
- Competition level (LOW / MEDIUM / HIGH)

Return ONLY valid JSON in this exact format:
{{
  "prompts": [
    {{
      "prompt": "What are the best options for [topic] in [country]?",
      "search_volume": 5000,
      "competition": "MEDIUM"
    }}
  ]
}}"""

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an AI search trends analyst. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,
            max_tokens=1200
        )

        text = response.choices[0].message.content
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
        else:
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                text = json_match.group(0)

        parsed = json.loads(text)
        prompts = parsed.get('prompts', [])
        # Sort by volume descending, return top 10
        prompts.sort(key=lambda x: x.get('search_volume', 0), reverse=True)
        return prompts[:10]

    def validate_credentials(self) -> bool:
        """Validate OpenAI API key"""
        try:
            # Try a minimal API call to validate key
            self.client.models.list()
            return True
        except Exception as e:
            logger.error(f"OpenAI credential validation failed: {e}")
            return False
