"""
Base class for all keyword data collectors.
Each data source (OpenAI, Google Ads, YouTube, etc.) inherits from this.
"""
from abc import ABC, abstractmethod
import time
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class BaseKeywordCollector(ABC):
    """Abstract base class for all keyword data collectors"""

    def __init__(self, credentials: Dict[str, Any]):
        """
        Initialize collector with API credentials

        Args:
            credentials: Dictionary containing API keys/tokens for this service
        """
        self.credentials = credentials
        self.source_name = self.__class__.__name__.replace("Collector", "").lower()

    @abstractmethod
    def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
        """
        Collect keyword data from this source

        Args:
            keywords: List of keywords to research
            countries: List of country codes to target

        Returns:
            Dictionary with collected data in standardized format:
            {
                "keyword1": {
                    "search_volume": int,
                    "competition": str,
                    "cpc": float,
                    "trends": {...},
                    "country_breakdown": {...}
                },
                ...
            }
        """
        pass

    def safe_collect(self, keywords: List[str], countries: List[str], max_retries: int = 3) -> Dict[str, Any]:
        """
        Wrapper around collect() with error handling and retries

        Args:
            keywords: List of keywords to research
            countries: List of country codes
            max_retries: Maximum number of retry attempts

        Returns:
            Dictionary with collected data, or error information
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"[{self.source_name}] Collecting data (attempt {attempt + 1}/{max_retries})")
                data = self.collect(keywords, countries)
                logger.info(f"[{self.source_name}] Successfully collected data for {len(data)} keywords")
                return {
                    "success": True,
                    "data": data,
                    "source": self.source_name
                }

            except Exception as e:
                logger.error(f"[{self.source_name}] Error on attempt {attempt + 1}: {str(e)}")

                # If this is the last attempt, return error info
                if attempt == max_retries - 1:
                    return {
                        "success": False,
                        "error": str(e),
                        "source": self.source_name
                    }

                # Exponential backoff before retry
                wait_time = 2 ** attempt
                logger.info(f"[{self.source_name}] Retrying in {wait_time} seconds...")
                time.sleep(wait_time)

        return {
            "success": False,
            "error": "Max retries exceeded",
            "source": self.source_name
        }

    def validate_credentials(self) -> bool:
        """
        Validate that required credentials are present
        Override in subclass if needed

        Returns:
            True if credentials are valid, False otherwise
        """
        return bool(self.credentials)
