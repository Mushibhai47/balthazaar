"""
TikTok keyword data collector
Uses unofficial TikTokApi to analyze hashtag trends and content performance
Note: This is a free but potentially unstable source
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class TikTokCollector(BaseKeywordCollector):
    """Collector for TikTok hashtag and trend data"""

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        # TikTok doesn't require API credentials for basic scraping
        # But we keep the structure consistent
        self.initialized = True

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        """
        Collect keyword data from TikTok

        Args:
            keywords: List of keywords to analyze (will be used as hashtags)
            countries: List of countries (limited support in unofficial API)

        Returns:
            Dictionary with TikTok trend insights
        """
        results = {}

        # Note: TikTokApi is fragile and breaks often due to TikTok's anti-scraping measures
        # For production, consider using Apify's TikTok scraper (paid but more reliable)

        try:
            from TikTokApi import TikTokApi

            # Initialize TikTok API (requires playwright browser)
            with TikTokApi() as api:
                for keyword in keywords:
                    logger.info(f"Collecting TikTok data for keyword: {keyword}")

                    try:
                        # Search for hashtag (TikTok uses hashtags for keywords)
                        hashtag = keyword.replace(" ", "").lower()

                        # Get hashtag info
                        hashtag_data = api.hashtag(name=hashtag)

                        # Get videos for this hashtag (limit to 30 to avoid rate limits)
                        videos = []
                        async for video in hashtag_data.videos(count=30):
                            videos.append(video)

                        # Analyze videos
                        keyword_insights = self._analyze_videos(keyword, videos, hashtag_data)
                        results[keyword] = keyword_insights

                    except Exception as e:
                        logger.error(f"Error collecting TikTok data for '{keyword}': {e}")
                        results[keyword] = self._create_error_entry(keyword, str(e))

        except ImportError:
            logger.warning("TikTokApi not installed. Install with: pip install TikTokApi")
            # Return placeholder data for all keywords
            for keyword in keywords:
                results[keyword] = self._create_unavailable_entry(keyword)

        except Exception as e:
            logger.error(f"TikTok API initialization failed: {e}")
            # Return error for all keywords
            for keyword in keywords:
                results[keyword] = self._create_error_entry(keyword, str(e))

        return results

    def _analyze_videos(self, keyword: str, videos: List[Any], hashtag_data: Any) -> Dict[str, Any]:
        """
        Analyze TikTok videos to extract insights

        Args:
            keyword: The search keyword
            videos: List of video objects from TikTokApi
            hashtag_data: Hashtag metadata

        Returns:
            Dictionary with keyword metrics
        """
        if not videos:
            return self._create_empty_entry(keyword)

        # Extract metrics from videos
        total_views = sum(video.get('stats', {}).get('playCount', 0) for video in videos)
        total_likes = sum(video.get('stats', {}).get('diggCount', 0) for video in videos)
        total_comments = sum(video.get('stats', {}).get('commentCount', 0) for video in videos)
        total_shares = sum(video.get('stats', {}).get('shareCount', 0) for video in videos)

        avg_views = total_views // len(videos) if videos else 0

        # Calculate engagement rate
        engagement_rate = ((total_likes + total_comments + total_shares) / total_views * 100) if total_views > 0 else 0

        # Determine competition based on video count
        video_count = len(videos)
        if video_count < 100:
            competition = "LOW"
        elif video_count < 1000:
            competition = "MEDIUM"
        else:
            competition = "HIGH"

        # Extract top creators
        top_creators = []
        seen_authors = set()
        for video in videos[:10]:
            author = video.get('author', {}).get('uniqueId', '')
            if author and author not in seen_authors:
                top_creators.append(author)
                seen_authors.add(author)

        return {
            "total_videos": video_count,
            "total_views": total_views,
            "avg_views_per_video": avg_views,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "total_shares": total_shares,
            "engagement_rate": round(engagement_rate, 2),
            "competition": competition,
            "insight": f"{video_count} videos with {avg_views:,} avg views and {engagement_rate:.1f}% engagement",
            "top_creators": top_creators[:5],
            "trending": avg_views > 100000,  # Consider trending if avg views > 100k
            "source": "tiktok"
        }

    def _create_empty_entry(self, keyword: str) -> Dict[str, Any]:
        """Create entry for keyword with no results"""
        return {
            "total_videos": 0,
            "total_views": 0,
            "avg_views_per_video": 0,
            "total_likes": 0,
            "total_comments": 0,
            "total_shares": 0,
            "engagement_rate": 0.0,
            "competition": "LOW",
            "insight": "No TikTok content found for this keyword",
            "top_creators": [],
            "trending": False,
            "source": "tiktok"
        }

    def _create_error_entry(self, keyword: str, error: str) -> Dict[str, Any]:
        """Create entry for keyword that encountered an error"""
        return {
            "total_videos": 0,
            "total_views": 0,
            "avg_views_per_video": 0,
            "total_likes": 0,
            "total_comments": 0,
            "total_shares": 0,
            "engagement_rate": 0.0,
            "competition": "UNKNOWN",
            "insight": f"Error: {error[:100]}",
            "top_creators": [],
            "trending": False,
            "error": error,
            "source": "tiktok"
        }

    def _create_unavailable_entry(self, keyword: str) -> Dict[str, Any]:
        """Create entry when TikTokApi is not available"""
        return {
            "total_videos": 0,
            "total_views": 0,
            "avg_views_per_video": 0,
            "total_likes": 0,
            "total_comments": 0,
            "total_shares": 0,
            "engagement_rate": 0.0,
            "competition": "UNKNOWN",
            "insight": "TikTokApi not installed. Run: pip install TikTokApi",
            "top_creators": [],
            "trending": False,
            "error": "TikTokApi module not found",
            "source": "tiktok"
        }

    def validate_credentials(self) -> bool:
        """TikTok scraping doesn't require credentials"""
        return True
