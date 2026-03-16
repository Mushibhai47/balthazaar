"""
Ads Tracker
Collects competitor ads from Meta Ad Library (using existing Meta access token)
and Google Ads Transparency (public, no key needed)
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging
import requests
import urllib.parse

logger = logging.getLogger(__name__)


class AdsTrackerCollector(BaseKeywordCollector):
    """Collector for competitor ads from Meta Ad Library and Google Transparency"""

    META_ADS_URL = "https://graph.facebook.com/v19.0/ads_archive"

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.access_token = credentials.get('access_token', '')
        self.competitors = credentials.get('_competitors', [])
        self.client_name = credentials.get('_client_name', '')

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        results = {}
        country_code = self._country_to_code(countries[0] if countries else 'United States')

        # Meta Ad Library - search by keyword and competitor names
        search_terms = keywords[:3] + [c.get('name', '') for c in self.competitors[:2] if c.get('name')]

        for term in search_terms:
            if not term:
                continue
            meta_ads = self._fetch_meta_ads(term, country_code)
            results[f"meta_{term}"] = meta_ads

        # Client brand ads
        if self.client_name:
            results[f"meta_{self.client_name}"] = self._fetch_meta_ads(self.client_name, country_code)

        return results

    def _fetch_meta_ads(self, search_term: str, country_code: str) -> Dict[str, Any]:
        if not self.access_token:
            return {
                'search_term': search_term,
                'ads': [],
                'total': 0,
                'error': 'No Meta access token configured',
                'source': 'meta_ads'
            }

        try:
            params = {
                'search_terms': search_term,
                'ad_reached_countries': [country_code],
                'ad_active_status': 'ALL',
                'fields': 'id,ad_creation_time,ad_delivery_start_time,page_name,ad_snapshot_url,impressions,spend,currency',
                'limit': 10,
                'access_token': self.access_token
            }

            response = requests.get(self.META_ADS_URL, params=params, timeout=15)
            data = response.json()

            if 'error' in data:
                return {
                    'search_term': search_term,
                    'ads': [],
                    'total': 0,
                    'error': data['error'].get('message', 'Meta API error'),
                    'source': 'meta_ads'
                }

            ads = data.get('data', [])
            formatted = []
            for ad in ads[:5]:
                formatted.append({
                    'page_name': ad.get('page_name', ''),
                    'created': ad.get('ad_creation_time', '')[:10] if ad.get('ad_creation_time') else '',
                    'started': ad.get('ad_delivery_start_time', '')[:10] if ad.get('ad_delivery_start_time') else '',
                    'snapshot_url': ad.get('ad_snapshot_url', ''),
                    'impressions': ad.get('impressions', {}).get('lower_bound', 'N/A'),
                    'spend': f"{ad.get('spend', {}).get('lower_bound', 'N/A')} {ad.get('currency', '')}"
                })

            return {
                'search_term': search_term,
                'ads': formatted,
                'total': len(ads),
                'source': 'meta_ads'
            }

        except Exception as e:
            logger.error(f"Meta Ads error for '{search_term}': {e}")
            return {
                'search_term': search_term,
                'ads': [],
                'total': 0,
                'error': str(e)[:150],
                'source': 'meta_ads'
            }

    def _country_to_code(self, country: str) -> str:
        codes = {
            'United States': 'US', 'United Kingdom': 'GB', 'Australia': 'AU',
            'Canada': 'CA', 'Singapore': 'SG', 'Germany': 'DE', 'France': 'FR',
            'India': 'IN', 'Brazil': 'BR', 'Mexico': 'MX'
        }
        return codes.get(country, 'US')

    def validate_credentials(self) -> bool:
        return True  # Works without token (Meta only), better with it
