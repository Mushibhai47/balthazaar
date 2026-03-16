"""
LinkedIn Jobs Collector
Scrapes LinkedIn public job listings for competitor companies
No credentials required - uses public LinkedIn job search
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging
import requests
import re
import urllib.parse

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


class LinkedInJobsCollector(BaseKeywordCollector):
    """Collector for LinkedIn job listings at client and competitor companies"""

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.competitors = credentials.get('_competitors', [])
        self.client_name = credentials.get('_client_name', '')

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        results = {}
        country = countries[0] if countries else 'United States'

        if self.client_name:
            results['_client'] = self._get_jobs(self.client_name, country)

        for comp in self.competitors[:5]:
            name = comp.get('name', '')
            if name:
                results[f"_competitor_{name}"] = self._get_jobs(name, country)

        if not results:
            results['_info'] = {'message': 'No companies configured', 'source': 'linkedin_jobs'}

        return results

    def _get_jobs(self, company: str, country: str) -> Dict[str, Any]:
        try:
            company_enc = urllib.parse.quote(company)
            country_enc = urllib.parse.quote(country)
            url = f"https://www.linkedin.com/jobs/search/?keywords={company_enc}&location={country_enc}&f_TPR=r2592000&sortBy=DD"

            response = requests.get(url, headers=HEADERS, timeout=15)
            jobs = self._parse_jobs(response.text)

            return {
                'company': company,
                'jobs_found': len(jobs),
                'recent_jobs': jobs[:5],
                'see_more_url': url,
                'source': 'linkedin_jobs'
            }
        except Exception as e:
            logger.error(f"LinkedIn jobs error for '{company}': {e}")
            return {
                'company': company,
                'jobs_found': 0,
                'recent_jobs': [],
                'error': str(e)[:150],
                'source': 'linkedin_jobs'
            }

    def _parse_jobs(self, html: str) -> List[Dict]:
        jobs = []
        try:
            titles = re.findall(r'class="base-search-card__title"[^>]*>\s*([^<]+)\s*<', html)
            companies = re.findall(r'class="base-search-card__subtitle"[^>]*>\s*([^<]+)\s*<', html)
            locations = re.findall(r'class="job-search-card__location"[^>]*>\s*([^<]+)\s*<', html)
            dates = re.findall(r'datetime="([^"]+)"', html)

            for i in range(min(len(titles), 10)):
                jobs.append({
                    'title': titles[i].strip() if i < len(titles) else '',
                    'company': companies[i].strip() if i < len(companies) else '',
                    'location': locations[i].strip() if i < len(locations) else '',
                    'posted': dates[i] if i < len(dates) else ''
                })
        except Exception as e:
            logger.error(f"LinkedIn parse error: {e}")
        return jobs

    def validate_credentials(self) -> bool:
        return True
