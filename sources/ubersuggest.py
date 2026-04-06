"""
Ubersuggest keyword data collector
Uses Selenium for authenticated scraping of Ubersuggest data
Requires login credentials to be stored in API credentials
"""
from sources.base import BaseKeywordCollector
from typing import Dict, List, Any
import logging
import time

logger = logging.getLogger(__name__)


class UbersuggestCollector(BaseKeywordCollector):
    """Collector for Ubersuggest SEO and keyword data"""

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.email = credentials.get("email")
        self.password = credentials.get("password")

        if not self.email or not self.password:
            logger.warning("Ubersuggest credentials (email/password) not provided")

    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        """
        Collect keyword data from Ubersuggest

        Args:
            keywords: List of keywords to analyze
            countries: List of countries (Ubersuggest supports regional data)

        Returns:
            Dictionary with SEO and keyword insights
        """
        results = {}

        if not self.email or not self.password:
            logger.error("Ubersuggest requires login credentials")
            for keyword in keywords:
                results[keyword] = self._create_error_entry(keyword, "No login credentials configured")
            return results

        # Selenium/Chrome not available on Replit — use requests-based scraping
        try:
            import requests
            from bs4 import BeautifulSoup

            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Referer': 'https://app.neilpatel.com/',
            })

            # Login via API
            login_resp = session.post(
                'https://app.neilpatel.com/api/user/login',
                json={'email': self.email, 'password': self.password},
                timeout=15
            )

            if login_resp.status_code != 200:
                raise Exception(f"Ubersuggest login failed: {login_resp.status_code} — {login_resp.text[:200]}")

            # Extract JWT token and set Authorization header
            try:
                body = login_resp.json()
                token = (body.get('data', {}) or {}).get('token') or body.get('token') or body.get('access_token')
                if not token:
                    token = session.cookies.get('id')
                if token:
                    session.headers.update({'Authorization': f'Bearer {token}'})
            except Exception:
                pass

            logger.info("Ubersuggest login successful")

            # Map country to Ubersuggest locId
            LOC_ID_MAP = {
                'Australia': '2036', 'Singapore': '2702', 'United Kingdom': '2826',
                'United States': '2840', 'Canada': '2124', 'New Zealand': '2554',
                'India': '2356', 'South Africa': '2710', 'Germany': '2276',
                'France': '2250', 'Spain': '2724', 'Brazil': '2076',
            }
            country = countries[0] if countries else 'United States'
            loc_id = LOC_ID_MAP.get(country, '2840')

            for keyword in keywords:
                try:
                    resp = session.get(
                        'https://app.neilpatel.com/api/keywords/keyword_overview',
                        params={'keyword': keyword, 'language': 'en', 'locId': loc_id},
                        timeout=15
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        results[keyword] = self._parse_api_response(keyword, data)
                    else:
                        results[keyword] = self._create_error_entry(keyword, f"API returned {resp.status_code}")
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"Ubersuggest error for '{keyword}': {e}")
                    results[keyword] = self._create_error_entry(keyword, str(e))

        except Exception as e:
            logger.error(f"Ubersuggest collector failed: {e}")
            for keyword in keywords:
                results[keyword] = self._create_error_entry(keyword, str(e))

        return results

    def _login(self, driver, wait):
        """Login to Ubersuggest"""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC

        # Go to login page
        driver.get("https://app.neilpatel.com/en/login")

        # Wait for and fill email
        email_field = wait.until(EC.presence_of_element_located((By.NAME, "email")))
        email_field.send_keys(self.email)

        # Fill password
        password_field = driver.find_element(By.NAME, "password")
        password_field.send_keys(self.password)

        # Click login button
        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        login_button.click()

        # Wait for dashboard to load
        time.sleep(5)
        logger.info("Successfully logged into Ubersuggest")

    def _scrape_keyword(self, driver, wait, keyword: str, country_code: str) -> Dict[str, Any]:
        """Scrape keyword data from Ubersuggest"""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC

        # Navigate to keyword overview
        url = f"https://app.neilpatel.com/en/ubersuggest/keyword_ideas?keyword={keyword}&locId={country_code}"
        driver.get(url)

        # Wait for data to load
        time.sleep(5)

        data = {}

        try:
            # Extract search volume
            search_volume_elem = driver.find_element(By.CSS_SELECTOR, "[data-test='search-volume']")
            data['search_volume'] = self._parse_number(search_volume_elem.text)

            # Extract SEO difficulty
            seo_difficulty_elem = driver.find_element(By.CSS_SELECTOR, "[data-test='seo-difficulty']")
            data['seo_difficulty'] = self._parse_number(seo_difficulty_elem.text)

            # Extract paid difficulty (CPC competition)
            paid_difficulty_elem = driver.find_element(By.CSS_SELECTOR, "[data-test='paid-difficulty']")
            data['paid_difficulty'] = self._parse_number(paid_difficulty_elem.text)

            # Extract CPC
            cpc_elem = driver.find_element(By.CSS_SELECTOR, "[data-test='cpc']")
            data['cpc'] = self._parse_currency(cpc_elem.text)

        except Exception as e:
            logger.warning(f"Could not extract all Ubersuggest metrics: {e}")

        return data

    def _get_country_code(self, country: str) -> str:
        """Get Ubersuggest location ID for country"""
        # Map common countries to Ubersuggest location IDs
        country_codes = {
            "United States": "2840",
            "United Kingdom": "2826",
            "Canada": "2124",
            "Australia": "2036",
            "Germany": "2276",
            "France": "2250",
            "Spain": "2724",
            "Italy": "2380",
            "India": "2356",
            "Brazil": "2076",
            "Mexico": "2484",
        }
        return country_codes.get(country, "2840")  # Default to US

    def _parse_number(self, text: str) -> int:
        """Parse number from Ubersuggest text (handles K, M suffixes)"""
        text = text.strip().replace(',', '')
        multiplier = 1

        if 'K' in text:
            multiplier = 1000
            text = text.replace('K', '')
        elif 'M' in text:
            multiplier = 1000000
            text = text.replace('M', '')

        try:
            return int(float(text) * multiplier)
        except (ValueError, AttributeError):
            return 0

    def _parse_currency(self, text: str) -> float:
        """Parse currency value from text"""
        text = text.strip().replace('$', '').replace(',', '')
        try:
            return float(text)
        except (ValueError, AttributeError):
            return 0.0

    def _parse_api_response(self, keyword: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Ubersuggest API JSON response"""
        kw_data = data.get('keyword', data)
        search_volume = kw_data.get('searchVolume', kw_data.get('sv', 0)) or 0
        cpc = kw_data.get('cpc', 0.0) or 0.0
        seo_difficulty = kw_data.get('seo', kw_data.get('seoDifficulty', 0)) or 0
        if seo_difficulty < 30:
            competition = "LOW"
        elif seo_difficulty < 60:
            competition = "MEDIUM"
        else:
            competition = "HIGH"
        return {
            "search_volume": int(search_volume),
            "seo_difficulty": int(seo_difficulty),
            "estimated_cpc": float(cpc),
            "competition": competition,
            "source": "ubersuggest",
            "keyword": keyword
        }

    def _analyze_keyword_data(self, keyword: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze scraped Ubersuggest data"""
        search_volume = data.get('search_volume', 0)
        seo_difficulty = data.get('seo_difficulty', 0)
        paid_difficulty = data.get('paid_difficulty', 0)
        cpc = data.get('cpc', 0.0)

        # Determine competition level based on SEO difficulty
        if seo_difficulty < 30:
            competition = "LOW"
        elif seo_difficulty < 60:
            competition = "MEDIUM"
        else:
            competition = "HIGH"

        return {
            "search_volume": search_volume,
            "seo_difficulty": seo_difficulty,
            "paid_difficulty": paid_difficulty,
            "cpc": cpc,
            "competition": competition,
            "insight": f"{search_volume:,} monthly searches, {seo_difficulty}/100 SEO difficulty, ${cpc:.2f} CPC",
            "opportunity_score": self._calculate_opportunity(search_volume, seo_difficulty),
            "source": "ubersuggest"
        }

    def _calculate_opportunity(self, volume: int, difficulty: int) -> float:
        """Calculate opportunity score (high volume + low difficulty = good)"""
        if difficulty == 0:
            return 0.0

        # Normalize volume (log scale) and invert difficulty
        volume_score = min(volume / 10000, 10)  # Cap at 10
        difficulty_score = (100 - difficulty) / 10  # Invert and scale to 10

        return round((volume_score + difficulty_score) / 2, 2)

    def _create_empty_entry(self, keyword: str) -> Dict[str, Any]:
        """Create entry for keyword with no results"""
        return {
            "search_volume": 0,
            "seo_difficulty": 0,
            "paid_difficulty": 0,
            "cpc": 0.0,
            "competition": "UNKNOWN",
            "insight": "No data found",
            "opportunity_score": 0.0,
            "source": "ubersuggest"
        }

    def _create_error_entry(self, keyword: str, error: str) -> Dict[str, Any]:
        """Create entry for keyword that encountered an error"""
        return {
            "search_volume": 0,
            "seo_difficulty": 0,
            "paid_difficulty": 0,
            "cpc": 0.0,
            "competition": "UNKNOWN",
            "insight": f"Error: {error[:100]}",
            "opportunity_score": 0.0,
            "error": error,
            "source": "ubersuggest"
        }

    def _create_unavailable_entry(self, keyword: str) -> Dict[str, Any]:
        """Create entry when Selenium is not available"""
        return {
            "search_volume": 0,
            "seo_difficulty": 0,
            "paid_difficulty": 0,
            "cpc": 0.0,
            "competition": "UNKNOWN",
            "insight": "Selenium not installed. Run: pip install selenium",
            "opportunity_score": 0.0,
            "error": "Selenium module not found",
            "source": "ubersuggest"
        }

    def validate_credentials(self) -> bool:
        """Validate Ubersuggest login credentials are present"""
        return bool(self.email and self.password)
