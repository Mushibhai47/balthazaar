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
            client_jobs = self._get_jobs(self.client_name, country)
            client_website = self.credentials.get('_client_website', '')
            client_website_jobs = self._get_website_jobs(self.client_name, client_website)
            if client_website_jobs.get('jobs_found', 0) > 0:
                client_jobs['website_jobs'] = client_website_jobs
            results['_client'] = client_jobs

        for idx, comp in enumerate(self.competitors):
            name = comp.get('name', '')
            website = comp.get('website', '')
            if name:
                job_data = self._get_jobs(name, country)
                # Also check company website
                website_jobs = self._get_website_jobs(name, website)
                if website_jobs.get('jobs_found', 0) > 0:
                    job_data['website_jobs'] = website_jobs
                results[f"_competitor_{idx}_{name}"] = job_data

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

    def _get_website_jobs(self, company: str, website: str) -> Dict[str, Any]:
        """Try to find jobs on company's own careers page"""
        if not website:
            return {}
        try:
            import re as _re
            domain = website.replace('https://', '').replace('http://', '').rstrip('/')
            # Try common career page paths
            career_urls = [
                f"https://{domain}/careers",
                f"https://{domain}/jobs",
                f"https://{domain}/work-with-us",
                f"https://{domain}/join-us",
            ]

            for url in career_urls:
                try:
                    resp = requests.get(url, headers=HEADERS, timeout=10)
                    if resp.status_code == 200 and len(resp.text) > 500:
                        # Extract job titles using common patterns
                        titles = _re.findall(
                            r'(?:job-title|position|role|opening)[^>]*>([^<]{5,60})<',
                            resp.text, _re.IGNORECASE
                        )
                        if not titles:
                            # Try h2/h3 tags as job titles
                            titles = _re.findall(r'<h[23][^>]*>([^<]{10,60})</h[23]>', resp.text)
                            titles = [t.strip() for t in titles if any(
                                w in t.lower() for w in ['manager', 'engineer', 'analyst', 'director', 'developer', 'specialist', 'consultant', 'head of', 'lead', 'officer']
                            )]

                        if titles:
                            return {
                                'company': company,
                                'source': 'company_website',
                                'careers_url': url,
                                'jobs_found': len(titles),
                                'job_titles': list(set(titles[:10]))
                            }
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Website jobs failed for {company}: {e}")
        return {}

    def validate_credentials(self) -> bool:
        return True
