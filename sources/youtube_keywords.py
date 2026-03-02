"""
YouTube keyword data collector
Uses YouTube Data API v3 to analyze keyword search volumes and video trends
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class YouTubeCollector(BaseKeywordCollector):
    """Collector for YouTube keyword and video trend data"""

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.api_key = credentials.get("api_key")
        if not self.api_key:
            raise ValueError("YouTube API key not found in credentials")

        self.youtube = build('youtube', 'v3', developerKey=self.api_key)

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        """
        Collect keyword data from YouTube

        Args:
            keywords: List of keywords to analyze
            countries: List of countries to target (ISO country codes)

        Returns:
            Dictionary with keyword insights from YouTube
        """
        results = {}

        for keyword in keywords:
            logger.info(f"Collecting YouTube data for keyword: {keyword}")

            try:
                # Search for videos matching this keyword
                search_response = self._search_videos(keyword, countries)

                # Analyze results
                keyword_data = self._analyze_search_results(keyword, search_response)
                results[keyword] = keyword_data

            except HttpError as e:
                logger.error(f"YouTube API error for keyword '{keyword}': {e}")
                results[keyword] = self._create_error_entry(keyword, str(e))
            except Exception as e:
                logger.error(f"Error collecting YouTube data for '{keyword}': {e}")
                results[keyword] = self._create_error_entry(keyword, str(e))

        return results

    def _search_videos(self, keyword: str, countries: List[str]) -> dict:
        """
        Search YouTube for videos matching keyword

        Args:
            keyword: Search query
            countries: List of country codes (uses first one)

        Returns:
            API response dict
        """
        search_params = {
            'q': keyword,
            'part': 'snippet',
            'type': 'video',
            'maxResults': 50,  # Get top 50 results
            'order': 'relevance',
            'safeSearch': 'none'
        }

        # Add region code if countries specified
        if countries and len(countries) > 0:
            # Convert country name to ISO 3166-1 alpha-2 code if needed
            region_code = self._get_region_code(countries[0])
            if region_code:
                search_params['regionCode'] = region_code

        request = self.youtube.search().list(**search_params)
        response = request.execute()

        return response

    def _get_region_code(self, country: str) -> str:
        """
        Convert country name to ISO 3166-1 alpha-2 code
        Returns empty string if not found
        """
        # Map common country names to ISO codes
        country_codes = {
            "United States": "US",
            "United Kingdom": "GB",
            "Canada": "CA",
            "Australia": "AU",
            "Germany": "DE",
            "France": "FR",
            "Spain": "ES",
            "Italy": "IT",
            "Japan": "JP",
            "China": "CN",
            "India": "IN",
            "Brazil": "BR",
            "Mexico": "MX",
            "South Korea": "KR",
            "Netherlands": "NL",
            "Sweden": "SE",
            "Norway": "NO",
            "Denmark": "DK",
            "Finland": "FI",
            "Poland": "PL",
            "Russia": "RU",
            "Turkey": "TR",
            "South Africa": "ZA",
            "New Zealand": "NZ",
            "Singapore": "SG",
            "Hong Kong": "HK",
            "Taiwan": "TW",
            "Thailand": "TH",
            "Malaysia": "MY",
            "Indonesia": "ID",
            "Philippines": "PH",
            "Vietnam": "VN",
            "Argentina": "AR",
            "Chile": "CL",
            "Colombia": "CO",
            "Peru": "PE",
            "Egypt": "EG",
            "Nigeria": "NG",
            "Kenya": "KE",
            "Israel": "IL",
            "UAE": "AE",
            "Saudi Arabia": "SA"
        }

        return country_codes.get(country, "")

    def _analyze_search_results(self, keyword: str, search_response: dict) -> Dict[str, Any]:
        """
        Analyze YouTube search results to extract insights

        Args:
            keyword: The search keyword
            search_response: YouTube API response

        Returns:
            Dictionary with keyword metrics
        """
        items = search_response.get('items', [])
        total_results = search_response.get('pageInfo', {}).get('totalResults', 0)

        if not items:
            return self._create_empty_entry(keyword)

        # Calculate metrics from top results
        video_ids = [item['id']['videoId'] for item in items if 'videoId' in item.get('id', {})]

        # Get detailed statistics for videos
        video_stats = self._get_video_statistics(video_ids)

        # Aggregate data
        total_views = sum(stats.get('viewCount', 0) for stats in video_stats.values())
        total_likes = sum(stats.get('likeCount', 0) for stats in video_stats.values())
        total_comments = sum(stats.get('commentCount', 0) for stats in video_stats.values())
        avg_views = total_views // len(video_stats) if video_stats else 0

        # Determine competition level based on number of results
        if total_results < 10000:
            competition = "LOW"
        elif total_results < 100000:
            competition = "MEDIUM"
        else:
            competition = "HIGH"

        # Calculate engagement rate
        engagement_rate = (total_likes + total_comments) / total_views if total_views > 0 else 0

        return {
            "total_videos": total_results,
            "top_50_views": total_views,
            "avg_views_per_video": avg_views,
            "total_engagement": total_likes + total_comments,
            "engagement_rate": round(engagement_rate * 100, 2),
            "competition": competition,
            "insight": f"{total_results:,} videos found with {avg_views:,} avg views",
            "top_channels": self._extract_top_channels(items)[:5],
            "source": "youtube"
        }

    def _get_video_statistics(self, video_ids: List[str]) -> Dict[str, Dict[str, int]]:
        """
        Get detailed statistics for a list of videos

        Args:
            video_ids: List of YouTube video IDs

        Returns:
            Dict mapping video IDs to their statistics
        """
        if not video_ids:
            return {}

        try:
            # YouTube API allows up to 50 IDs per request
            request = self.youtube.videos().list(
                part='statistics',
                id=','.join(video_ids[:50])
            )
            response = request.execute()

            stats = {}
            for item in response.get('items', []):
                video_id = item['id']
                statistics = item.get('statistics', {})
                stats[video_id] = {
                    'viewCount': int(statistics.get('viewCount', 0)),
                    'likeCount': int(statistics.get('likeCount', 0)),
                    'commentCount': int(statistics.get('commentCount', 0))
                }

            return stats

        except HttpError as e:
            logger.error(f"Error fetching video statistics: {e}")
            return {}

    def _extract_top_channels(self, items: List[dict]) -> List[str]:
        """Extract channel names from search results"""
        channels = []
        seen = set()

        for item in items:
            channel_title = item.get('snippet', {}).get('channelTitle', '')
            if channel_title and channel_title not in seen:
                channels.append(channel_title)
                seen.add(channel_title)

        return channels

    def _create_empty_entry(self, keyword: str) -> Dict[str, Any]:
        """Create entry for keyword with no results"""
        return {
            "total_videos": 0,
            "top_50_views": 0,
            "avg_views_per_video": 0,
            "total_engagement": 0,
            "engagement_rate": 0.0,
            "competition": "LOW",
            "insight": "No videos found for this keyword",
            "top_channels": [],
            "source": "youtube"
        }

    def _create_error_entry(self, keyword: str, error: str) -> Dict[str, Any]:
        """Create entry for keyword that encountered an error"""
        return {
            "total_videos": 0,
            "top_50_views": 0,
            "avg_views_per_video": 0,
            "total_engagement": 0,
            "engagement_rate": 0.0,
            "competition": "UNKNOWN",
            "insight": f"Error collecting data: {error[:100]}",
            "top_channels": [],
            "error": error,
            "source": "youtube"
        }

    def validate_credentials(self) -> bool:
        """Validate YouTube API key"""
        try:
            # Try a minimal search to validate key
            request = self.youtube.search().list(
                q='test',
                part='snippet',
                maxResults=1
            )
            response = request.execute()
            return True
        except Exception as e:
            logger.error(f"YouTube credential validation failed: {e}")
            return False
