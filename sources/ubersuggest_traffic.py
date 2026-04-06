"""
Ubersuggest Traffic Collector
Fetches website traffic overview for client and competitors from Ubersuggest
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging
import requests
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Candidate API endpoints for traffic data (tried in order)
TRAFFIC_ENDPOINTS = [
    "/traffic_analyzer/overview",
    "/traffic_analyzer",
    "/domain/overview",
    "/traffic/stats",
]


def _clean_domain(url: str) -> str:
    """Extract bare hostname from any URL form"""
    url = url.strip()
    if not url:
        return url
    if '://' not in url:
        url = 'https://' + url
    parsed = urlparse(url)
    return (parsed.netloc or parsed.path.split('/')[0]).lower().lstrip('www.')


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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://app.neilpatel.com/',
            'Origin': 'https://app.neilpatel.com',
        })
        self._logged_in = False
        self._working_endpoint = None

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
            logger.warning(f"Ubersuggest traffic login returned {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"Ubersuggest traffic login failed: {e}")
        return False

    def _fetch_traffic(self, domain: str, label: str, entity_type: str, country_code: str = 'us') -> Dict[str, Any]:
        """Fetch traffic overview for a domain"""
        domain = _clean_domain(domain)
        if not domain:
            return {'domain': domain, 'label': label, 'type': entity_type, 'error': 'Empty domain'}

        # Try cached working endpoint first, then probe all candidates
        endpoints_to_try = ([self._working_endpoint] if self._working_endpoint else []) + \
                           [e for e in TRAFFIC_ENDPOINTS if e != self._working_endpoint]

        for endpoint in endpoints_to_try:
            try:
                resp = self.session.get(
                    f"{self.BASE_URL}{endpoint}",
                    params={'domain': domain, 'country': country_code, 'currency': 'USD'},
                    timeout=15
                )
                if resp.status_code == 200:
                    self._working_endpoint = endpoint
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
                elif resp.status_code not in (403, 404):
                    # Unexpected error — stop trying
                    logger.warning(f"Ubersuggest traffic {endpoint} returned {resp.status_code} for {domain}")
                    break
            except Exception as e:
                logger.warning(f"Ubersuggest traffic request failed for {domain}: {e}")
                break

        return {'domain': domain, 'label': label, 'type': entity_type, 'error': 'Endpoint not available'}

    COUNTRY_CODE_MAP = {
        'Australia': 'au', 'Singapore': 'sg', 'United Kingdom': 'gb',
        'United States': 'us', 'Canada': 'ca', 'New Zealand': 'nz',
        'India': 'in', 'South Africa': 'za', 'Germany': 'de',
        'France': 'fr', 'Spain': 'es', 'Brazil': 'br',
    }

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        results = {}

        if not self._login():
            return {}

        country_code = self.COUNTRY_CODE_MAP.get(countries[0] if countries else 'United States', 'us')

        if self.client_website:
            results['client'] = self._fetch_traffic(
                self.client_website,
                label=self.client_website,
                entity_type='client',
                country_code=country_code
            )

        for comp in self.competitors[:4]:
            website = comp.get('website', '')
            name = comp.get('name', website)
            if website:
                key = f"competitor_{name}"
                results[key] = self._fetch_traffic(website, label=name, entity_type='competitor', country_code=country_code)

        return results

    def validate_credentials(self) -> bool:
        return self._login()
