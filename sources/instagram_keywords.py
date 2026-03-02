"""
Instagram keyword data collector
Uses web scraping to analyze hashtag performance and content trends
Note: Instagram actively blocks scrapers - this is a best-effort implementation
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging
import requests
from bs4 import BeautifulSoup
import json
import re

logger = logging.getLogger(__name__)


class InstagramCollector(BaseKeywordCollector):
    """Collector for Instagram hashtag and content data"""

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        # Instagram scraping doesn't require credentials for public data
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9'
        })

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        """
        Collect keyword data from Instagram

        Args:
            keywords: List of keywords to analyze (will be used as hashtags)
            countries: List of countries (Instagram doesn't support regional filtering)

        Returns:
            Dictionary with Instagram hashtag insights
        """
        results = {}

        for keyword in keywords:
            logger.info(f"Collecting Instagram data for keyword: {keyword}")

            try:
                # Convert keyword to hashtag format
                hashtag = keyword.replace(" ", "").lower()

                # Scrape Instagram hashtag page
                hashtag_data = self._scrape_hashtag(hashtag)

                # Analyze data
                keyword_insights = self._analyze_hashtag_data(keyword, hashtag_data)
                results[keyword] = keyword_insights

            except Exception as e:
                logger.error(f"Error collecting Instagram data for '{keyword}': {e}")
                results[keyword] = self._create_error_entry(keyword, str(e))

        return results

    def _scrape_hashtag(self, hashtag: str) -> Dict[str, Any]:
        """
        Scrape Instagram hashtag page for public data

        Args:
            hashtag: The hashtag to scrape (without #)

        Returns:
            Dictionary with scraped data
        """
        url = f"https://www.instagram.com/explore/tags/{hashtag}/"

        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()

            # Instagram embeds data in a script tag as JSON
            soup = BeautifulSoup(response.text, 'html.parser')

            # Find the script tag containing hashtag data
            # Instagram uses <script type="application/ld+json"> for structured data
            json_data = None
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    json_data = json.loads(script.string)
                    break
                except json.JSONDecodeError:
                    continue

            # Try to extract data from window._sharedData as fallback
            if not json_data:
                for script in soup.find_all('script'):
                    if script.string and 'window._sharedData' in script.string:
                        # Extract JSON from window._sharedData = {...};
                        match = re.search(r'window\._sharedData = ({.*?});', script.string)
                        if match:
                            json_data = json.loads(match.group(1))
                            break

            if json_data:
                return self._parse_instagram_json(json_data, hashtag)
            else:
                # Fallback: try to extract basic info from HTML
                return self._parse_instagram_html(soup, hashtag)

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error scraping Instagram #{hashtag}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error parsing Instagram data for #{hashtag}: {e}")
            raise

    def _parse_instagram_json(self, json_data: dict, hashtag: str) -> Dict[str, Any]:
        """Parse Instagram JSON data structure"""
        # Instagram's data structure varies, try multiple paths
        try:
            # Try to find hashtag info in entry_data
            if 'entry_data' in json_data:
                tag_page = json_data.get('entry_data', {}).get('TagPage', [{}])[0]
                hashtag_data = tag_page.get('graphql', {}).get('hashtag', {})

                post_count = hashtag_data.get('edge_hashtag_to_media', {}).get('count', 0)

                # Get sample posts
                edges = hashtag_data.get('edge_hashtag_to_media', {}).get('edges', [])
                posts = [edge.get('node', {}) for edge in edges]

                return {
                    'post_count': post_count,
                    'posts': posts,
                    'hashtag': hashtag
                }

            # Fallback structure
            return {
                'post_count': 0,
                'posts': [],
                'hashtag': hashtag
            }

        except Exception as e:
            logger.warning(f"Error parsing Instagram JSON: {e}")
            return {
                'post_count': 0,
                'posts': [],
                'hashtag': hashtag
            }

    def _parse_instagram_html(self, soup: BeautifulSoup, hashtag: str) -> Dict[str, Any]:
        """Fallback HTML parsing when JSON extraction fails"""
        # Try to find post count in meta tags
        meta_content = soup.find('meta', property='og:description')
        post_count = 0

        if meta_content:
            content = meta_content.get('content', '')
            # Extract number from text like "1.2M posts"
            match = re.search(r'([\d,]+\.?\d*[KMB]?)\s+posts', content)
            if match:
                count_str = match.group(1)
                post_count = self._parse_count(count_str)

        return {
            'post_count': post_count,
            'posts': [],
            'hashtag': hashtag
        }

    def _parse_count(self, count_str: str) -> int:
        """Parse Instagram count strings like '1.2M' to integers"""
        count_str = count_str.replace(',', '')
        multiplier = 1

        if 'K' in count_str:
            multiplier = 1000
            count_str = count_str.replace('K', '')
        elif 'M' in count_str:
            multiplier = 1000000
            count_str = count_str.replace('M', '')
        elif 'B' in count_str:
            multiplier = 1000000000
            count_str = count_str.replace('B', '')

        try:
            return int(float(count_str) * multiplier)
        except ValueError:
            return 0

    def _analyze_hashtag_data(self, keyword: str, hashtag_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze scraped Instagram data to extract insights

        Args:
            keyword: The search keyword
            hashtag_data: Scraped hashtag data

        Returns:
            Dictionary with keyword metrics
        """
        post_count = hashtag_data.get('post_count', 0)
        posts = hashtag_data.get('posts', [])

        if post_count == 0 and not posts:
            return self._create_empty_entry(keyword)

        # Calculate metrics from sample posts
        total_likes = sum(post.get('edge_liked_by', {}).get('count', 0) for post in posts)
        total_comments = sum(post.get('edge_media_to_comment', {}).get('count', 0) for post in posts)
        avg_engagement = (total_likes + total_comments) / len(posts) if posts else 0

        # Determine competition level
        if post_count < 10000:
            competition = "LOW"
        elif post_count < 100000:
            competition = "MEDIUM"
        elif post_count < 1000000:
            competition = "HIGH"
        else:
            competition = "VERY HIGH"

        return {
            "total_posts": post_count,
            "sample_size": len(posts),
            "avg_likes": total_likes // len(posts) if posts else 0,
            "avg_comments": total_comments // len(posts) if posts else 0,
            "avg_engagement": round(avg_engagement, 2),
            "competition": competition,
            "insight": f"{post_count:,} posts using this hashtag",
            "trending": post_count > 1000000,  # Trending if over 1M posts
            "source": "instagram"
        }

    def _create_empty_entry(self, keyword: str) -> Dict[str, Any]:
        """Create entry for keyword with no results"""
        return {
            "total_posts": 0,
            "sample_size": 0,
            "avg_likes": 0,
            "avg_comments": 0,
            "avg_engagement": 0.0,
            "competition": "LOW",
            "insight": "No Instagram posts found for this hashtag",
            "trending": False,
            "source": "instagram"
        }

    def _create_error_entry(self, keyword: str, error: str) -> Dict[str, Any]:
        """Create entry for keyword that encountered an error"""
        # Check if it's a blocking/rate limit error
        if "429" in str(error) or "blocked" in str(error).lower():
            insight = "Instagram blocked the request (rate limited)"
        else:
            insight = f"Error: {error[:100]}"

        return {
            "total_posts": 0,
            "sample_size": 0,
            "avg_likes": 0,
            "avg_comments": 0,
            "avg_engagement": 0.0,
            "competition": "UNKNOWN",
            "insight": insight,
            "trending": False,
            "error": error,
            "source": "instagram"
        }

    def validate_credentials(self) -> bool:
        """Instagram scraping doesn't require credentials"""
        return True
