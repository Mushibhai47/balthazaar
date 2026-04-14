"""
NLP Sentiment Analyzer
Analyzes YouTube comments for keyword-related sentiment
Uses VADER (free, no API key required for analysis)
YouTube API key used to fetch comments
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class SentimentCollector(BaseKeywordCollector):
    """NLP sentiment analysis on YouTube comments related to keywords"""

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.youtube_api_key = credentials.get('api_key', '')
        self.competitors = credentials.get('_competitors', [])
        self.client_name = credentials.get('_client_name', '')

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        # Store country for use in news fetching
        from sources.google_news import COUNTRY_LOCALE_MAP
        country = countries[0] if countries else 'United States'
        locale = COUNTRY_LOCALE_MAP.get(country, ('en-US', 'US', 'US:en'))
        self._hl, self._gl, self._ceid = locale

        results = {}

        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            analyzer = SentimentIntensityAnalyzer()
        except ImportError:
            logger.warning("vaderSentiment not installed, using basic scoring")
            analyzer = None

        for keyword in keywords[:5]:  # Limit API calls
            comments = self._get_youtube_comments(keyword)

            if not comments:
                results[keyword] = {
                    'positive_pct': 0,
                    'neutral_pct': 0,
                    'negative_pct': 0,
                    'top_positive': [],
                    'top_negative': [],
                    'total_analyzed': 0,
                    'source': 'sentiment'
                }
                continue

            scored = []
            for c in comments:
                text = c.get('text', '')
                if analyzer:
                    score = analyzer.polarity_scores(text)['compound']
                else:
                    score = self._basic_score(text)

                sentiment = 'positive' if score > 0.05 else ('negative' if score < -0.05 else 'neutral')
                scored.append({**c, 'score': score, 'sentiment': sentiment})

            total = len(scored)
            pos = sorted([c for c in scored if c['sentiment'] == 'positive'], key=lambda x: x['score'], reverse=True)
            neg = sorted([c for c in scored if c['sentiment'] == 'negative'], key=lambda x: x['score'])
            neu = [c for c in scored if c['sentiment'] == 'neutral']

            results[keyword] = {
                'positive_pct': round(len(pos) / total * 100) if total else 0,
                'neutral_pct': round(len(neu) / total * 100) if total else 0,
                'negative_pct': round(len(neg) / total * 100) if total else 0,
                'top_positive': [{'text': c['text'][:200], 'score': round(c['score'], 3), 'source': c.get('video_title', 'YouTube')} for c in pos[:5]],
                'top_negative': [{'text': c['text'][:200], 'score': round(c['score'], 3), 'source': c.get('video_title', 'YouTube')} for c in neg[:5]],
                'total_analyzed': total,
                'source': 'sentiment'
            }

        # Brand-based sentiment (client + each competitor)
        brands = []
        if self.client_name:
            brands.append({'name': self.client_name, 'type': 'client'})
        for comp in self.competitors[:3]:
            if comp.get('name'):
                brands.append({'name': comp['name'], 'type': 'competitor'})

        for brand in brands:
            brand_key = f"brand_{brand['name'].lower().replace(' ', '_')}"
            # Search for brand mentions and analyze sentiment
            brand_texts = self._fetch_brand_texts(brand['name'])
            if brand_texts:
                sentiment_result = self._analyze_texts(brand_texts, analyzer)
            else:
                sentiment_result = {
                    'positive_pct': 0, 'neutral_pct': 0, 'negative_pct': 0,
                    'top_positive': [], 'top_negative': [], 'total_analyzed': 0,
                    'source': 'sentiment'
                }
            sentiment_result['brand_name'] = brand['name']
            sentiment_result['brand_type'] = brand['type']
            sentiment_result['is_brand'] = True
            results[brand_key] = sentiment_result

        return results

    def _fetch_brand_texts(self, brand_name: str) -> list:
        """Fetch text snippets about a brand from Google News RSS"""
        try:
            import feedparser
            import urllib.parse
            query = urllib.parse.quote(f'"{brand_name}"')
            url = f"https://news.google.com/rss/search?q={query}&hl={getattr(self, '_hl', 'en-US')}&gl={getattr(self, '_gl', 'US')}&ceid={getattr(self, '_ceid', 'US:en')}"
            feed = feedparser.parse(url)
            texts = []
            for entry in feed.entries[:15]:
                text = entry.get('summary', entry.get('title', ''))
                if text:
                    import re as _re
                    text = _re.sub(r'<[^>]+>', '', text).strip()
                if text:
                    texts.append({'text': text[:300], 'title': entry.get('title', ''),
                                  'link': entry.get('link', ''), 'source': entry.get('source', {}).get('title', '')})
            return texts
        except Exception as e:
            logger.warning(f"Brand text fetch failed for {brand_name}: {e}")
            return []

    def _analyze_texts(self, texts: list, analyzer=None) -> Dict[str, Any]:
        """Analyze sentiment for a list of text dicts (each with a 'text' key)"""
        if analyzer is None:
            try:
                from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
                analyzer = SentimentIntensityAnalyzer()
            except ImportError:
                analyzer = None

        scored = []
        for item in texts:
            text = item.get('text', '')
            if analyzer:
                score = analyzer.polarity_scores(text)['compound']
            else:
                score = self._basic_score(text)
            sentiment = 'positive' if score > 0.05 else ('negative' if score < -0.05 else 'neutral')
            scored.append({**item, 'score': score, 'sentiment': sentiment})

        total = len(scored)
        pos = sorted([c for c in scored if c['sentiment'] == 'positive'], key=lambda x: x['score'], reverse=True)
        neg = sorted([c for c in scored if c['sentiment'] == 'negative'], key=lambda x: x['score'])
        neu = [c for c in scored if c['sentiment'] == 'neutral']

        return {
            'positive_pct': round(len(pos) / total * 100) if total else 0,
            'neutral_pct': round(len(neu) / total * 100) if total else 0,
            'negative_pct': round(len(neg) / total * 100) if total else 0,
            'top_positive': [{'text': c['text'][:200], 'score': round(c['score'], 3), 'source': c.get('source', '')} for c in pos[:5]],
            'top_negative': [{'text': c['text'][:200], 'score': round(c['score'], 3), 'source': c.get('source', '')} for c in neg[:5]],
            'total_analyzed': total,
            'source': 'sentiment'
        }

    def _get_youtube_comments(self, keyword: str) -> List[Dict]:
        if not self.youtube_api_key:
            return []
        try:
            from googleapiclient.discovery import build
            youtube = build('youtube', 'v3', developerKey=self.youtube_api_key)

            search = youtube.search().list(
                q=keyword, part='snippet', type='video', maxResults=5
            ).execute()

            video_ids = [
                item['id']['videoId']
                for item in search.get('items', [])
                if 'videoId' in item.get('id', {})
            ]

            comments = []
            for vid_id in video_ids[:3]:
                try:
                    vid_title = next(
                        (i['snippet']['title'] for i in search['items'] if i['id'].get('videoId') == vid_id), ''
                    )
                    resp = youtube.commentThreads().list(
                        part='snippet', videoId=vid_id, maxResults=25, order='relevance'
                    ).execute()
                    for item in resp.get('items', []):
                        text = item['snippet']['topLevelComment']['snippet'].get('textDisplay', '')
                        if text:
                            comments.append({'text': text, 'video_title': vid_title})
                except Exception:
                    continue

            return comments
        except Exception as e:
            logger.error(f"YouTube comments error for '{keyword}': {e}")
            return []

    def _basic_score(self, text: str) -> float:
        pos = ['great', 'good', 'excellent', 'amazing', 'love', 'best', 'perfect', 'awesome', 'fantastic', 'helpful', 'recommend']
        neg = ['bad', 'terrible', 'awful', 'worst', 'hate', 'horrible', 'useless', 'poor', 'disappointing', 'waste', 'scam']
        t = text.lower()
        p = sum(1 for w in pos if w in t)
        n = sum(1 for w in neg if w in t)
        return (p - n) / (p + n) if (p + n) > 0 else 0.0

    def validate_credentials(self) -> bool:
        return True  # Works without YouTube key (returns empty), better with it
