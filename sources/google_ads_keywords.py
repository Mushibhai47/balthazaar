"""
Google Ads keyword data collector
Uses Google Ads API Keyword Planner for real search volume data
Requires: developer_token, client_id, client_secret, refresh_token
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class GoogleAdsCollector(BaseKeywordCollector):
    """Collector for Google Ads keyword performance data"""

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.developer_token = credentials.get('developer_token', '')
        self.manager_customer_id = credentials.get('manager_customer_id', '').replace('-', '')
        self.client_customer_id = credentials.get('client_customer_id', '').replace('-', '')
        self.client_id = credentials.get('client_id', '')
        self.client_secret = credentials.get('client_secret', '')
        self.refresh_token = credentials.get('refresh_token', '')

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        results = {}

        if not all([self.client_id, self.client_secret, self.refresh_token]):
            logger.warning("Google Ads OAuth not configured yet (need client_id, client_secret, refresh_token)")
            for kw in keywords:
                results[kw] = {
                    'status': 'pending_oauth',
                    'message': 'Google Ads connected (developer token received). OAuth setup pending — will be available soon.',
                    'source': 'google_ads'
                }
            return results

        try:
            from google.ads.googleads.client import GoogleAdsClient

            config = {
                'developer_token': self.developer_token,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'refresh_token': self.refresh_token,
                'login_customer_id': self.manager_customer_id,
                'use_proto_plus': True
            }

            client = GoogleAdsClient.load_from_dict(config)
            kpis = client.get_service("KeywordPlanIdeaService")
            request = client.get_type("GenerateKeywordIdeasRequest")
            request.customer_id = self.client_customer_id

            seed = client.get_type("KeywordSeed")
            seed.keywords.extend(keywords)
            request.keyword_seed = seed

            response = kpis.generate_keyword_ideas(request=request)

            for idea in response:
                m = idea.keyword_idea_metrics
                results[idea.text] = {
                    'search_volume': m.avg_monthly_searches,
                    'competition': str(m.competition.name),
                    'competition_index': m.competition_index,
                    'low_cpc': round(m.low_top_of_page_bid_micros / 1_000_000, 2) if m.low_top_of_page_bid_micros else 0,
                    'high_cpc': round(m.high_top_of_page_bid_micros / 1_000_000, 2) if m.high_top_of_page_bid_micros else 0,
                    'source': 'google_ads'
                }

        except ImportError:
            for kw in keywords:
                results[kw] = {'error': 'google-ads package not installed', 'source': 'google_ads'}
        except Exception as e:
            logger.error(f"Google Ads API error: {e}")
            for kw in keywords:
                results[kw] = {'error': str(e)[:200], 'source': 'google_ads'}

        return results

    def validate_credentials(self) -> bool:
        return bool(self.developer_token)
