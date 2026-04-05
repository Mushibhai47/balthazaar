"""
Ubersuggest AI Search Visibility Collector
Fetches AI brand visibility data — brand visibility %, industry rank,
top prompts, competitor comparison — from Ubersuggest AI Search Visibility feature.
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging
import requests

logger = logging.getLogger(__name__)


class UbersuggestAIVisibilityCollector(BaseKeywordCollector):
    """Fetches AI Search Visibility metrics from Ubersuggest for client and competitors"""

    BASE_URL = "https://app.neilpatel.com/api"

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.email = credentials.get('email', '')
        self.password = credentials.get('password', '')
        self.client_name = credentials.get('_client_name', '')
        self.client_website = credentials.get('_client_website', '')
        self.competitors = credentials.get('_competitors', [])
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        })
        self._logged_in = False

    def _login(self) -> bool:
        if self._logged_in:
            return True
        if not self.email or not self.password:
            return False
        try:
            resp = self.session.post(
                f"{self.BASE_URL}/user/login",
                json={'email': self.email, 'password': self.password},
                timeout=15
            )
            if resp.status_code == 200:
                try:
                    body = resp.json()
                    token = (body.get('data', {}) or {}).get('token') or body.get('token') or body.get('access_token')
                    if token:
                        self.session.headers.update({'Authorization': f'Bearer {token}'})
                except Exception:
                    pass
                self._logged_in = True
                return True
            logger.warning(f"Ubersuggest login returned {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"Ubersuggest login failed: {e}")
        return False

    def _fetch_ai_visibility(self, domain: str, label: str, entity_type: str) -> Dict[str, Any]:
        """Fetch AI Search Visibility for a domain"""
        domain = domain.replace('https://', '').replace('http://', '').rstrip('/')
        result = {
            'domain': domain,
            'label': label,
            'type': entity_type,
            'brand_visibility_pct': 0,
            'industry_rank': None,
            'total_analyzed': 0,
            'top_prompts': [],
            'competitor_comparison': [],
        }
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/ai_search/overview",
                params={'domain': domain},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                overview = data.get('overview', data)
                result['brand_visibility_pct'] = overview.get('brandVisibility', overview.get('visibility', 0))
                result['industry_rank'] = overview.get('industryRank', overview.get('rank'))
                result['total_analyzed'] = overview.get('totalResponses', overview.get('analyzed', 0))

            resp2 = self.session.get(
                f"{self.BASE_URL}/ai_search/prompts",
                params={'domain': domain, 'limit': 10},
                timeout=15
            )
            if resp2.status_code == 200:
                data2 = resp2.json()
                prompts = data2.get('prompts', data2.get('data', []))
                result['top_prompts'] = [
                    {
                        'prompt': p.get('prompt', p.get('query', '')),
                        'rank': p.get('rank', p.get('avgRank')),
                        'mentions': p.get('mentions', 0)
                    }
                    for p in prompts[:10]
                ]

            resp3 = self.session.get(
                f"{self.BASE_URL}/ai_search/brands",
                params={'domain': domain, 'limit': 10},
                timeout=15
            )
            if resp3.status_code == 200:
                data3 = resp3.json()
                brands = data3.get('brands', data3.get('data', []))
                result['competitor_comparison'] = [
                    {
                        'brand': b.get('brand', b.get('name', '')),
                        'visibility': b.get('visibility', 0),
                        'mentions': b.get('mentions', 0),
                        'avg_rank': b.get('avgRank', b.get('avg_rank'))
                    }
                    for b in brands[:10]
                ]
        except Exception as e:
            logger.warning(f"AI visibility fetch failed for {domain}: {e}")
            result['error'] = str(e)[:100]
        return result

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        results = {}
        if not self._login():
            return {}
        if self.client_website:
            results['client'] = self._fetch_ai_visibility(
                self.client_website, self.client_name or self.client_website, 'client'
            )
        for comp in self.competitors[:4]:
            website = comp.get('website', '')
            name = comp.get('name', website)
            if website:
                results[f"competitor_{name}"] = self._fetch_ai_visibility(website, name, 'competitor')
        return results

    def validate_credentials(self) -> bool:
        return self._login()
