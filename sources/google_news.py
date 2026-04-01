"""
Google News RSS brand monitoring
Collects news articles mentioning keywords and competitors
No API key required - uses public RSS feeds
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging
import urllib.parse
import requests

logger = logging.getLogger(__name__)


class GoogleNewsCollector(BaseKeywordCollector):
    """Collector for Google News brand and competitor monitoring"""

    BASE_URL = "https://news.google.com/rss/search"

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.client_name = credentials.get('_client_name', '')
        self.competitors = credentials.get('_competitors', [])

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        results = {}

        # Top 5 keywords in news
        for keyword in keywords[:5]:
            results[keyword] = self._fetch_news(keyword)

        # Client brand news
        if self.client_name:
            results[f"_brand_{self.client_name}"] = self._fetch_news(self.client_name, label="client_brand")

        # Competitor brand news
        for comp in self.competitors[:3]:
            name = comp.get('name', '')
            if name:
                results[f"_competitor_{name}"] = self._fetch_news(name, label="competitor")

        # Brand-based news (client + competitors)
        brands = []
        if self.client_name:
            brands.append({'name': self.client_name, 'label': 'client_brand'})
        for comp in self.competitors[:3]:
            if comp.get('name'):
                brands.append({'name': comp['name'], 'label': 'competitor'})

        for brand in brands:
            brand_key = f"brand_{brand['name'].lower().replace(' ', '_')}"
            fetched = self._fetch_news(brand['name'])
            results[brand_key] = {
                'query': brand['name'],
                'label': brand['label'],
                'articles': fetched.get('articles', []),
                'article_count': fetched.get('article_count', 0),
                'is_brand': True
            }

        return results

    def _fetch_news(self, query: str, label: str = "keyword") -> Dict[str, Any]:
        try:
            import feedparser
            encoded = urllib.parse.quote(query)
            url = f"{self.BASE_URL}?q={encoded}&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(url)

            articles = []
            for entry in feed.entries[:10]:
                articles.append({
                    'title': entry.get('title', ''),
                    'link': entry.get('link', ''),
                    'published': entry.get('published', ''),
                    'source': entry.get('source', {}).get('title', 'Unknown'),
                    'summary': entry.get('summary', '')[:300] if entry.get('summary') else ''
                })

            return {
                'query': query,
                'article_count': len(articles),
                'articles': articles,
                'label': label,
                'source': 'google_news'
            }
        except Exception as e:
            logger.error(f"Google News error for '{query}': {e}")
            return {
                'query': query,
                'article_count': 0,
                'articles': [],
                'error': str(e),
                'label': label,
                'source': 'google_news'
            }

    def validate_credentials(self) -> bool:
        return True  # No credentials needed
