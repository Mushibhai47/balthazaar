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
                # The 'id' cookie contains the JWT — set it as Bearer token
                id_token = self.session.cookies.get('id')
                if id_token:
                    self.session.headers.update({'Authorization': f'Bearer {id_token}'})
                self._logged_in = True
                return True
            logger.warning(f"Ubersuggest traffic login returned {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"Ubersuggest traffic login failed: {e}")
        return False

    def _fetch_traffic(self, domain: str, label: str, entity_type: str, country_code: str = 'us', loc_id: str = '2840') -> Dict[str, Any]:
        """Fetch traffic overview for a domain"""
        domain = _clean_domain(domain)
        if not domain:
            return {'domain': domain, 'label': label, 'type': entity_type, 'error': 'Empty domain'}

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/domain_overview",
                params={'domain': domain, 'lang': 'en', 'locId': loc_id},
                timeout=15
            )
            logger.warning(f"[T] {domain} {resp.status_code} auth={bool(self.session.headers.get('Authorization'))} body={resp.text[:80]}")
            if resp.status_code != 200:
                return {'domain': domain, 'label': label, 'type': entity_type, 'error': f'HTTP {resp.status_code}'}

            data = resp.json()
            # Get latest month traffic from domainTraffic time series
            domain_traffic = data.get('domainTraffic', {})
            latest_month = max(domain_traffic.keys()) if domain_traffic else None
            latest = domain_traffic.get(latest_month, {}) if latest_month else {}

            return {
                'domain': domain,
                'label': label,
                'type': entity_type,
                'organic_monthly': data.get('traffic', latest.get('searchTraffic', 0)),
                'paid_monthly': data.get('paidTraffic', latest.get('paidTraffic', 0)),
                'total_monthly': data.get('traffic', 0),
                'domain_score': data.get('domainAuthority', 0),
                'backlinks': data.get('backlinks', 0),
                'keywords_count': data.get('organic', 0),
            }
        except Exception as e:
            logger.warning(f"Ubersuggest traffic fetch failed for {domain}: {e}")
            return {'domain': domain, 'label': label, 'type': entity_type, 'error': str(e)[:100]}

    COUNTRY_CODE_MAP = {
        'Australia': 'au', 'Singapore': 'sg', 'United Kingdom': 'gb',
        'United States': 'us', 'Canada': 'ca', 'New Zealand': 'nz',
        'India': 'in', 'South Africa': 'za', 'Germany': 'de',
        'France': 'fr', 'Spain': 'es', 'Brazil': 'br',
    }

    LOC_ID_MAP = {
        'Australia': '2036', 'Singapore': '2702', 'United Kingdom': '2826',
        'United States': '2840', 'Canada': '2124', 'New Zealand': '2554',
        'India': '2356', 'South Africa': '2710', 'Germany': '2276',
        'France': '2250', 'Spain': '2724', 'Brazil': '2076',
    }

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        results = {}

        if not self._login():
            return {}

        country = countries[0] if countries else 'United States'
        country_code = self.COUNTRY_CODE_MAP.get(country, 'us')
        loc_id = self.LOC_ID_MAP.get(country, '2840')

        if self.client_website:
            results['client'] = self._fetch_traffic(
                self.client_website,
                label=self.client_website,
                entity_type='client',
                country_code=country_code,
                loc_id=loc_id
            )

        for comp in self.competitors[:4]:
            website = comp.get('website', '')
            name = comp.get('name', website)
            if website:
                key = f"competitor_{name}"
                results[key] = self._fetch_traffic(website, label=name, entity_type='competitor', country_code=country_code, loc_id=loc_id)

        return results

    def validate_credentials(self) -> bool:
        return self._login()
