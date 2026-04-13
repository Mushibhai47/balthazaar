"""
Reviews Collector
Scrapes public reviews from Trustpilot, Google Business, and generic review pages
No API key required
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging
import requests
import re

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


class ReviewsCollector(BaseKeywordCollector):
    """Scrapes public reviews for client and competitors"""

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.client_name = credentials.get('_client_name', '')
        self.client_review_url = credentials.get('_client_review_url', '')
        self.competitors = credentials.get('_competitors', [])

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        results = {}

        if self.client_review_url:
            results['_client'] = self._fetch_reviews(self.client_review_url, self.client_name, 'client')

        for idx, comp in enumerate(self.competitors[:5]):
            name = comp.get('name', f'Competitor {idx + 1}')
            review_url = comp.get('review_page_url', '')
            key = f"_competitor_{idx}_{name}"
            if review_url:
                results[key] = self._fetch_reviews(review_url, name, 'competitor')
            else:
                results[key] = {
                    'entity_name': name, 'entity_type': 'competitor',
                    'review_url': '', 'reviews': [], 'total_reviews': 0,
                    'avg_rating': None, 'message': 'No review page configured',
                    'source': 'reviews'
                }

        return results

    def _fetch_reviews(self, url: str, entity_name: str, entity_type: str) -> Dict[str, Any]:
        if not url or not url.strip():
            return {
                'entity_name': entity_name, 'entity_type': entity_type,
                'review_url': url, 'reviews': [], 'total_reviews': 0,
                'avg_rating': None, 'message': 'No review URL provided', 'source': 'reviews'
            }
        try:
            if 'trustpilot.com' in url:
                return self._scrape_trustpilot(url, entity_name, entity_type)
            else:
                return self._scrape_generic(url, entity_name, entity_type)
        except Exception as e:
            logger.warning(f"Reviews fetch failed for {entity_name}: {e}")
            return {
                'entity_name': entity_name, 'entity_type': entity_type,
                'review_url': url, 'reviews': [], 'total_reviews': 0,
                'avg_rating': None, 'error': str(e)[:150], 'source': 'reviews'
            }

    def _scrape_trustpilot(self, url: str, entity_name: str, entity_type: str) -> Dict[str, Any]:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        html = resp.text

        # Extract average rating
        avg_rating = None
        rating_match = re.search(r'"ratingValue"\s*:\s*"?([\d.]+)"?', html)
        if rating_match:
            try:
                avg_rating = float(rating_match.group(1))
            except Exception:
                pass

        # Extract total review count
        total_reviews = 0
        count_match = re.search(r'"reviewCount"\s*:\s*(\d+)', html)
        if count_match:
            total_reviews = int(count_match.group(1))

        # Extract review snippets
        reviews = []
        # Trustpilot structured data
        review_blocks = re.findall(
            r'"reviewBody"\s*:\s*"([^"]{10,500})".*?"ratingValue"\s*:\s*"?([\d.]+)"?',
            html, re.DOTALL
        )
        for text, rating in review_blocks[:10]:
            reviews.append({
                'text': text.replace('\\n', ' ').replace('\\"', '"')[:300],
                'rating': float(rating) if rating else None,
                'source': 'Trustpilot'
            })

        # Fallback: look for review text patterns
        if not reviews:
            texts = re.findall(r'<p[^>]*data-service-review-text[^>]*>([^<]{20,400})</p>', html)
            for t in texts[:10]:
                reviews.append({'text': t.strip()[:300], 'rating': None, 'source': 'Trustpilot'})

        return {
            'entity_name': entity_name, 'entity_type': entity_type,
            'review_url': url, 'reviews': reviews[:10],
            'total_reviews': total_reviews or len(reviews),
            'avg_rating': avg_rating, 'platform': 'Trustpilot', 'source': 'reviews'
        }

    def _scrape_generic(self, url: str, entity_name: str, entity_type: str) -> Dict[str, Any]:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        html = resp.text

        # Try JSON-LD structured data first
        avg_rating = None
        total_reviews = 0
        rating_match = re.search(r'"ratingValue"\s*:\s*"?([\d.]+)"?', html)
        count_match = re.search(r'"reviewCount"\s*:\s*(\d+)', html)
        if rating_match:
            try:
                avg_rating = float(rating_match.group(1))
            except Exception:
                pass
        if count_match:
            total_reviews = int(count_match.group(1))

        # Extract review bodies
        reviews = []
        review_bodies = re.findall(r'"reviewBody"\s*:\s*"([^"]{20,500})"', html)
        for text in review_bodies[:10]:
            reviews.append({
                'text': text.replace('\\n', ' ').replace('\\"', '"')[:300],
                'rating': None, 'source': url
            })

        # Fallback: look for common review patterns
        if not reviews:
            patterns = [
                r'<div[^>]+class="[^"]*review[^"]*"[^>]*>([^<]{30,400})<',
                r'<p[^>]+class="[^"]*review[^"]*"[^>]*>([^<]{30,400})<',
            ]
            for pattern in patterns:
                found = re.findall(pattern, html, re.IGNORECASE)
                for t in found[:5]:
                    if len(t.strip()) > 20:
                        reviews.append({'text': t.strip()[:300], 'rating': None, 'source': url})
                if reviews:
                    break

        platform = 'Google' if 'google.com/maps' in url else 'Unknown'

        return {
            'entity_name': entity_name, 'entity_type': entity_type,
            'review_url': url, 'reviews': reviews[:10],
            'total_reviews': total_reviews or len(reviews),
            'avg_rating': avg_rating, 'platform': platform, 'source': 'reviews',
            'message': 'No reviews found — review page may require JavaScript' if not reviews else ''
        }

    def validate_credentials(self) -> bool:
        return True
