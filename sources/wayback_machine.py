"""
Wayback Machine website amendments tracker
Detects changes in competitor websites over the past 30 days
No API key required - uses public Wayback Machine CDX API
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class WaybackMachineCollector(BaseKeywordCollector):
    """Collector for website change detection using Wayback Machine"""

    CDX_API = "https://web.archive.org/cdx/search/cdx"

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.client_website = credentials.get('_client_website', '')
        self.competitors = credentials.get('_competitors', [])

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        results = {}

        # Check client website
        if self.client_website:
            results['_client'] = self._check_website(self.client_website, 'client')

        # Check competitor websites
        for idx, comp in enumerate(self.competitors[:5]):
            website = comp.get('website', '')
            name = comp.get('name') or website  # fallback to URL if name is empty
            if website:
                results[f"_competitor_{idx}_{name}"] = self._check_website(website, 'competitor', name)

        if not results:
            results['_info'] = {
                'message': 'No websites configured to monitor',
                'source': 'wayback_machine'
            }

        return results

    def _check_website(self, url: str, entity_type: str, label: str = '') -> Dict[str, Any]:
        try:
            clean_url = url.replace('https://', '').replace('http://', '').rstrip('/')
            from_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')

            params = {
                'url': clean_url + '/*',
                'output': 'json',
                'limit': 20,
                'from': from_date,
                'fl': 'timestamp,statuscode,urlkey',
                'collapse': 'digest',
                'filter': 'statuscode:200'
            }

            response = requests.get(self.CDX_API, params=params, timeout=15)

            if response.status_code != 200:
                return {'error': f'API {response.status_code}', 'source': 'wayback_machine', 'url': url}

            try:
                data = response.json()
            except Exception:
                return {'snapshots': 0, 'changes': [], 'message': 'No data', 'source': 'wayback_machine', 'url': url}

            if len(data) <= 1:
                return {
                    'snapshots': 0,
                    'changes': [],
                    'message': 'No recent snapshots in last 30 days',
                    'source': 'wayback_machine',
                    'type': entity_type,
                    'label': label or url,
                    'url': url
                }

            snapshots = []
            for row in data[1:15]:
                if len(row) >= 3:
                    ts = row[0]
                    page_url = row[2].replace(',', '/').replace(')', '').replace('http://', '').replace('https://', '')
                    try:
                        date_str = datetime.strptime(ts[:8], '%Y%m%d').strftime('%b %d, %Y')
                    except Exception:
                        date_str = ts[:8]
                    change = {
                        'date': date_str,
                        'timestamp': ts,
                        'page': page_url[:80],
                        'archive_url': f"https://web.archive.org/web/{ts}/{url}"
                    }
                    # Generate a human-readable description
                    page_url_lower = page_url.lower()
                    if 'pricing' in page_url_lower:
                        change['description'] = 'Pricing page updated'
                    elif 'product' in page_url_lower:
                        change['description'] = 'Product page modified'
                    elif 'about' in page_url_lower:
                        change['description'] = 'About page updated'
                    elif 'contact' in page_url_lower:
                        change['description'] = 'Contact information updated'
                    elif 'blog' in page_url_lower or 'news' in page_url_lower:
                        change['description'] = 'New blog/news content added'
                    elif 'career' in page_url_lower or 'job' in page_url_lower:
                        change['description'] = 'Careers/jobs page updated'
                    elif page_url == '/' or page_url == '':
                        change['description'] = 'Homepage content changed'
                    else:
                        change['description'] = f'Page content updated'
                    snapshots.append(change)

            return {
                'snapshots': len(snapshots),
                'changes': snapshots[:5],
                'message': f"{len(snapshots)} page version(s) captured in last 30 days",
                'source': 'wayback_machine',
                'type': entity_type,
                'label': label or url,
                'url': url
            }

        except Exception as e:
            logger.error(f"Wayback Machine error for {url}: {e}")
            return {'error': str(e)[:150], 'source': 'wayback_machine', 'url': url}

    def validate_credentials(self) -> bool:
        return True  # No credentials needed
