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


COUNTRY_LOCALE_MAP = {
    'Australia': ('en-AU', 'AU', 'AU:en'),
    'Singapore': ('en-SG', 'SG', 'SG:en'),
    'Malaysia': ('en-MY', 'MY', 'MY:en'),
    'United Kingdom': ('en-GB', 'GB', 'GB:en'),
    'United States': ('en-US', 'US', 'US:en'),
    'Canada': ('en-CA', 'CA', 'CA:en'),
    'New Zealand': ('en-NZ', 'NZ', 'NZ:en'),
    'India': ('en-IN', 'IN', 'IN:en'),
    'South Africa': ('en-ZA', 'ZA', 'ZA:en'),
    'Germany': ('de', 'DE', 'DE:de'),
    'France': ('fr', 'FR', 'FR:fr'),
    'Spain': ('es', 'ES', 'ES:es'),
    'Brazil': ('pt-BR', 'BR', 'BR:pt-419'),
    'Indonesia': ('id-ID', 'ID', 'ID:id'),
    'Philippines': ('en-PH', 'PH', 'PH:en'),
    'Thailand': ('th-TH', 'TH', 'TH:th'),
    'Vietnam': ('vi-VN', 'VN', 'VN:vi'),
    'Japan': ('ja-JP', 'JP', 'JP:ja'),
    'South Korea': ('ko-KR', 'KR', 'KR:ko'),
    'China': ('zh-CN', 'CN', 'CN:zh-Hans'),
    'Hong Kong': ('zh-HK', 'HK', 'HK:zh-Hant'),
    'UAE': ('en-AE', 'AE', 'AE:en'),
    'Saudi Arabia': ('ar-SA', 'SA', 'SA:ar'),
    'Nigeria': ('en-NG', 'NG', 'NG:en'),
    'Kenya': ('en-KE', 'KE', 'KE:en'),
    'Mexico': ('es-419', 'MX', 'MX:es-419'),
    'Argentina': ('es-419', 'AR', 'AR:es-419'),
    'Netherlands': ('nl-NL', 'NL', 'NL:nl'),
    'Italy': ('it-IT', 'IT', 'IT:it'),
    'Portugal': ('pt-PT', 'PT', 'PT:pt-150'),
    'Sweden': ('sv-SE', 'SE', 'SE:sv'),
    'Norway': ('nb-NO', 'NO', 'NO:nb'),
    'Denmark': ('da-DK', 'DK', 'DK:da'),
    'Poland': ('pl-PL', 'PL', 'PL:pl'),
    'Russia': ('ru-RU', 'RU', 'RU:ru'),
    'Turkey': ('tr-TR', 'TR', 'TR:tr'),
    'Israel': ('he-IL', 'IL', 'IL:he'),
    'Pakistan': ('en-PK', 'PK', 'PK:en'),
    'Bangladesh': ('en-BD', 'BD', 'BD:en'),
    'Sri Lanka': ('en-LK', 'LK', 'LK:en'),
    'Egypt': ('ar-EG', 'EG', 'EG:ar'),
}


class GoogleNewsCollector(BaseKeywordCollector):
    """Collector for Google News brand and competitor monitoring"""

    BASE_URL = "https://news.google.com/rss/search"

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.client_name = credentials.get('_client_name', '')
        self.competitors = credentials.get('_competitors', [])
        self.period_start = credentials.get('_period_start')  # ISO date string e.g. "2025-01-01"
        self.period_end = credentials.get('_period_end')

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        # Determine locale from first country in list
        country = countries[0] if countries else 'United States'
        locale = COUNTRY_LOCALE_MAP.get(country, ('en-US', 'US', 'US:en'))
        self._hl, self._gl, self._ceid = locale

        results = {}

        # Top 5 keywords in news
        for keyword in keywords[:5]:
            results[keyword] = self._fetch_news(keyword)

        # Brand-based news (client + competitors)
        brands = []
        if self.client_name:
            brands.append({'name': self.client_name, 'label': 'client_brand'})
        for comp in self.competitors[:3]:
            if comp.get('name'):
                brands.append({'name': comp['name'], 'label': 'competitor'})

        for brand in brands:
            brand_key = f"brand_{brand['name'].lower().replace(' ', '_')}"
            articles = self._fetch_news(brand['name'])
            results[brand_key] = {
                'query': brand['name'],
                'label': brand['label'],
                'articles': articles,
                'article_count': len(articles),
                'is_brand': True
            }

        return results

    def _parse_rss_date(self, date_str: str):
        """Parse RSS date string to datetime, return None on failure."""
        if not date_str:
            return None
        from email.utils import parsedate_to_datetime
        try:
            return parsedate_to_datetime(date_str)
        except Exception:
            pass
        # Try ISO format as fallback
        from datetime import datetime as dt
        for fmt in ('%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d'):
            try:
                return dt.strptime(date_str[:19], fmt)
            except Exception:
                pass
        return None

    def _fetch_news(self, query: str, label: str = "keyword") -> Dict[str, Any]:
        try:
            import feedparser
            encoded = urllib.parse.quote(query)
            url = f"{self.BASE_URL}?q={encoded}&hl={getattr(self, '_hl', 'en-US')}&gl={getattr(self, '_gl', 'US')}&ceid={getattr(self, '_ceid', 'US:en')}"
            feed = feedparser.parse(url)

            import html as html_mod
            from datetime import datetime as dt, timezone

            # Build period filter bounds if set
            period_start_dt = None
            period_end_dt = None
            if self.period_start:
                try:
                    period_start_dt = dt.fromisoformat(self.period_start).replace(tzinfo=timezone.utc)
                except Exception:
                    pass
            if self.period_end:
                try:
                    period_end_dt = dt.fromisoformat(self.period_end).replace(tzinfo=timezone.utc)
                except Exception:
                    pass

            articles = []
            for entry in feed.entries[:20]:
                pub_str = entry.get('published', '')
                pub_dt = self._parse_rss_date(pub_str)

                # Filter by period if period is set
                if period_start_dt or period_end_dt:
                    if pub_dt:
                        # Make naive datetimes timezone-aware for comparison
                        if pub_dt.tzinfo is None:
                            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                        if period_start_dt and pub_dt < period_start_dt:
                            continue
                        if period_end_dt and pub_dt > period_end_dt:
                            continue
                    # If we can't parse the date and period filter is active, skip the article
                    elif period_start_dt or period_end_dt:
                        continue

                articles.append({
                    'title': html_mod.unescape(entry.get('title', '')),
                    'link': entry.get('link', ''),
                    'published': pub_str,
                    'source': html_mod.unescape(entry.get('source', {}).get('title', 'Unknown')),
                    'summary': html_mod.unescape(entry.get('summary', '')[:300]) if entry.get('summary') else ''
                })
                if len(articles) >= 10:
                    break

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
