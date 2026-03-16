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

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
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

        return results

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
