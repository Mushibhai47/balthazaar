"""
YouTube keyword data collector
Uses YouTube Data API v3 to analyze keyword search volumes and video trends
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging
import re
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
        self.competitors = credentials.get('_competitors', [])
        self.client_name = credentials.get('_client_name', '')

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

        # Competitor channel videos
        for comp in self.competitors[:4]:
            comp_name = comp.get('name', '')
            youtube_url = comp.get('youtube_url', '')
            if not comp_name:
                continue
            try:
                channel_data = self._get_channel_videos(comp_name, youtube_url)
                results[f"_channel_{comp_name}"] = channel_data
            except Exception as e:
                logger.warning(f"Channel fetch failed for {comp_name}: {e}")
                results[f"_channel_{comp_name}"] = {
                    'company': comp_name, 'videos': [], 'error': str(e)[:100], 'is_channel': True
                }

        # Client channel too
        if self.client_name:
            client_comp = {'name': self.client_name, 'youtube_url': ''}
            try:
                results['_channel_client'] = self._get_channel_videos(self.client_name, '')
                results['_channel_client']['is_client'] = True
            except Exception as e:
                logger.warning(f"Client channel fetch failed: {e}")

        return results

    def _get_channel_videos(self, company_name: str, youtube_url: str) -> Dict[str, Any]:
        """Fetch recent videos from a competitor/client YouTube channel"""
        channel_id = None

        # Try to extract channel ID from URL
        import re as _re
        if youtube_url:
            channel_match = _re.search(r'channel/(UC[\w-]+)', youtube_url)
            handle_match = _re.search(r'@([\w.-]+)', youtube_url)
            user_match = _re.search(r'/user/([\w.-]+)', youtube_url)

            if channel_match:
                channel_id = channel_match.group(1)
            elif handle_match:
                handle = handle_match.group(1)
                # Use forHandle API (most accurate for @handle URLs)
                try:
                    ch_resp = self.youtube.channels().list(
                        forHandle=f'@{handle}', part='id'
                    ).execute()
                    if ch_resp.get('items'):
                        channel_id = ch_resp['items'][0]['id']
                except Exception:
                    pass
                # Fallback: search by handle text
                if not channel_id:
                    try:
                        search_resp = self.youtube.search().list(
                            q=handle, part='snippet', type='channel', maxResults=1
                        ).execute()
                        if search_resp.get('items'):
                            channel_id = search_resp['items'][0]['snippet']['channelId']
                    except Exception:
                        pass
            elif user_match:
                try:
                    ch_resp = self.youtube.channels().list(
                        forUsername=user_match.group(1), part='id'
                    ).execute()
                    if ch_resp.get('items'):
                        channel_id = ch_resp['items'][0]['id']
                except Exception:
                    pass

        # If no channel ID yet, search by company name
        if not channel_id:
            try:
                search_resp = self.youtube.search().list(
                    q=f"{company_name} official", part='snippet', type='channel', maxResults=1
                ).execute()
                if search_resp.get('items'):
                    channel_id = search_resp['items'][0]['snippet']['channelId']
            except Exception as e:
                logger.warning(f"Channel search failed for {company_name}: {e}")
                return {'company': company_name, 'videos': [], 'total_videos': 0, 'is_channel': True}

        if not channel_id:
            return {'company': company_name, 'videos': [], 'total_videos': 0, 'is_channel': True}

        # Get recent videos from channel
        try:
            videos_resp = self.youtube.search().list(
                channelId=channel_id,
                part='snippet',
                order='date',
                type='video',
                maxResults=10
            ).execute()

            video_items = videos_resp.get('items', [])
            video_ids = [v['id']['videoId'] for v in video_items if v.get('id', {}).get('videoId')]

            # Get stats
            stats = self._get_video_statistics(video_ids) if video_ids else {}

            videos = []
            for item in video_items[:8]:
                vid_id = item.get('id', {}).get('videoId', '')
                snippet = item.get('snippet', {})
                s = stats.get(vid_id, {})
                videos.append({
                    'title': snippet.get('title', ''),
                    'published': snippet.get('publishedAt', '')[:10],
                    'views': s.get('viewCount', 0),
                    'likes': s.get('likeCount', 0),
                    'comments': s.get('commentCount', 0),
                    'engagement_rate': round((s.get('likeCount', 0) + s.get('commentCount', 0)) / max(s.get('viewCount', 1), 1) * 100, 2),
                    'url': f"https://youtube.com/watch?v={vid_id}" if vid_id else ''
                })

            avg_views = sum(v['views'] for v in videos) // max(len(videos), 1)
            avg_engagement = round(sum(v['engagement_rate'] for v in videos) / max(len(videos), 1), 2)

            return {
                'company': company_name,
                'channel_id': channel_id,
                'videos': videos,
                'total_videos': len(videos),
                'avg_views': avg_views,
                'avg_engagement_rate': avg_engagement,
                'is_channel': True
            }
        except Exception as e:
            logger.error(f"Video fetch failed for channel {channel_id}: {e}")
            return {'company': company_name, 'channel_id': channel_id, 'videos': [], 'total_videos': 0, 'is_channel': True, 'error': str(e)[:100]}

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
