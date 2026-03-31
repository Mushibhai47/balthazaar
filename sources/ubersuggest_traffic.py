"""
Ubersuggest Traffic Collector
Fetches website traffic overview for client and competitors from Ubersuggest
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging
import requests

logger = logging.getLogger(__name__)


class UbersuggestTrafficCollector(BaseKeywordCollector):
    """Fetches organic + paid traffic estimates from Ubersuggest for client & competitors"""

    BASE_URL = "https://app.neilpatel.com/api"

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.email = credentials.get('email', '')
        self.password = credentials.get('password', '')
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
                self._logged_in = True
                return True
        except Exception as e:
            logger.warning(f"Ubersuggest login failed: {e}")
        return False

    def _fetch_traffic(self, domain: str, label: str, entity_type: str) -> Dict[str, Any]:
        """Fetch traffic overview for a domain"""
        domain = domain.replace('https://', '').replace('http://', '').rstrip('/')
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/traffic/overview",
                params={'domain': domain, 'country': 'us', 'currency': 'USD'},
                timeout=15
            )
            if resp.status_code != 200:
                return {'domain': domain, 'label': label, 'type': entity_type, 'error': f'HTTP {resp.status_code}'}

            data = resp.json()
            overview = data.get('overview', data)
            return {
                'domain': domain,
                'label': label,
                'type': entity_type,
                'organic_monthly': overview.get('organic', overview.get('organicTraffic', 0)),
                'paid_monthly': overview.get('paid', overview.get('paidTraffic', 0)),
                'total_monthly': overview.get('total', overview.get('totalTraffic', 0)),
                'domain_score': overview.get('domainScore', overview.get('da', 0)),
                'backlinks': overview.get('backlinks', 0),
                'keywords_count': overview.get('keywords', 0),
            }
        except Exception as e:
            logger.warning(f"Traffic fetch failed for {domain}: {e}")
            return {'domain': domain, 'label': label, 'type': entity_type, 'error': str(e)[:100]}

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        results = {}

        if not self._login():
            # Return empty structure — no credentials
            return {}

        # Client website
        if self.client_website:
            results['client'] = self._fetch_traffic(
                self.client_website,
                label=self.client_website,
                entity_type='client'
            )

        # Competitors
        for comp in self.competitors[:4]:
            website = comp.get('website', '')
            name = comp.get('name', website)
            if website:
                key = f"competitor_{name}"
                results[key] = self._fetch_traffic(website, label=name, entity_type='competitor')

        return results

    def validate_credentials(self) -> bool:
        return self._login()
