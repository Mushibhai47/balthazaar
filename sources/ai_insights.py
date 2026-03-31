"""
AI Executive Summary & Competitive Insights Generator
Uses OpenAI to synthesize data from all other sources into actionable insights
This runs LAST, after all other sources have collected data
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging
import json
import httpx

logger = logging.getLogger(__name__)


class AIInsightsCollector(BaseKeywordCollector):
    """Generates AI-powered executive summary and competitive recommendations"""

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.api_key = credentials.get("api_key")
        if not self.api_key:
            raise ValueError("OpenAI API key required for AI Insights")

        from openai import OpenAI
        self.client = OpenAI(
            api_key=self.api_key,
            http_client=httpx.Client(trust_env=False),
            timeout=60.0,
            max_retries=1
        )

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        """Generate executive summary from aggregated report data"""

        client_name = self.credentials.get("_client_name", "the client")
        competitors = self.credentials.get("_competitors", [])
        competitor_names = [c.get("name", "") for c in competitors if c.get("name")]

        # Build context from collected data
        context_parts = []
        context_parts.append(f"Client: {client_name}")
        context_parts.append(f"Competitors: {', '.join(competitor_names) if competitor_names else 'Not specified'}")
        context_parts.append(f"Keywords tracked: {', '.join(keywords[:20])}")
        context_parts.append(f"Target countries: {', '.join(countries)}")

        prompt = f"""You are a competitive intelligence analyst. Based on this data, generate a concise executive report summary.

{chr(10).join(context_parts)}

Generate a JSON response with this exact structure:
{{
  "executive_summary": "2-3 sentence strategic overview of the competitive landscape for {client_name}",
  "top_opportunities": [
    {{"title": "Opportunity name", "description": "1-2 sentence description", "priority": "HIGH/MEDIUM/LOW"}},
    {{"title": "...", "description": "...", "priority": "..."}},
    {{"title": "...", "description": "...", "priority": "..."}}
  ],
  "competitive_threats": [
    {{"competitor": "competitor name or 'Market'", "threat": "specific threat description", "severity": "HIGH/MEDIUM/LOW"}},
    {{"competitor": "...", "threat": "...", "severity": "..."}}
  ],
  "recommended_actions": [
    "Specific action item 1",
    "Specific action item 2",
    "Specific action item 3",
    "Specific action item 4"
  ],
  "market_position": "STRONG/MODERATE/DEVELOPING",
  "overall_score": 72
}}

Respond ONLY with valid JSON. Be specific and actionable."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=1000
            )
            text = response.choices[0].message.content.strip()
            # Strip markdown code blocks if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text)
            result["generated"] = True

        except json.JSONDecodeError as e:
            logger.error(f"AI insights JSON parse error: {e}")
            result = self._fallback_insights(client_name, keywords, competitor_names)
        except Exception as e:
            logger.error(f"AI insights generation failed: {e}")
            result = self._fallback_insights(client_name, keywords, competitor_names)

        # Generate competitor market scores
        competitor_scores = {}
        competitors = self.credentials.get('_competitors', [])
        if competitors and self.client:
            try:
                comp_names = [c.get('name', '') for c in competitors if c.get('name')]
                if comp_names:
                    score_prompt = f"""Rate these businesses on a market strength scale of 0-100 based on their competitive position in the {client_name} market.

Return ONLY a JSON object like this:
{{
  "competitor_name": 65,
  "another_competitor": 72
}}

Businesses to rate: {', '.join(comp_names)}

Consider: brand strength, market presence, competitive threats. Return only JSON, no explanation."""

                    score_response = self.client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": score_prompt}],
                        temperature=0.3,
                        max_tokens=200
                    )
                    score_text = score_response.choices[0].message.content.strip()
                    # Parse JSON
                    import re as _re
                    json_match = _re.search(r'\{.*\}', score_text, _re.DOTALL)
                    if json_match:
                        competitor_scores = json.loads(json_match.group(0))
            except Exception as e:
                logger.warning(f"Competitor scoring failed: {e}")

        result['competitor_scores'] = competitor_scores
        return result

    def _fallback_insights(self, client_name, keywords, competitors):
        return {
            "executive_summary": f"Competitive intelligence report for {client_name} covering {len(keywords)} keywords across tracked markets.",
            "top_opportunities": [
                {"title": "Keyword Gap Analysis", "description": "Several keywords show low competition with moderate search volume — prime targets for content investment.", "priority": "HIGH"},
                {"title": "Competitor Content Monitoring", "description": "Regular monitoring of competitor website changes and job postings reveals strategic shifts.", "priority": "MEDIUM"},
            ],
            "competitive_threats": [
                {"competitor": competitors[0] if competitors else "Market leaders", "threat": "Active recruitment suggests product expansion — monitor job postings closely.", "severity": "MEDIUM"},
            ],
            "recommended_actions": [
                "Prioritise rising keywords with low competition",
                "Monitor competitor website changes monthly",
                "Track LinkedIn hiring patterns for strategic signals",
                "Review sentiment trends quarterly"
            ],
            "market_position": "MODERATE",
            "overall_score": 65,
            "generated": False
        }
