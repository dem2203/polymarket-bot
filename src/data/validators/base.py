"""
Base Validator - Hızlı, asenkron data validation için base class.

Design Principles:
- NEVER block trading (always fallback)
- FAST async execution (<500ms target)
- Aggressive caching (5-10 min)
- Short timeouts (2-3 sec max)
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

logger = logging.getLogger("bot.validators")


class BaseValidator(ABC):
    """Base class for all data validators."""
    
    def __init__(self, cache_ttl: int = 300):
        """
        Args:
            cache_ttl: Cache time-to-live in seconds (default: 5 minutes)
        """
        self.cache: Dict[str, tuple[Any, float]] = {}  # {key: (data, timestamp)}
        self.cache_ttl = cache_ttl
        self.api_timeout = 3.0  # 3 second timeout
        
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get cached data if still valid."""
        if key in self.cache:
            data, timestamp = self.cache[key]
            age = time.time() - timestamp
            if age < self.cache_ttl:
                logger.debug(f"Cache HIT: {key} (age: {age:.0f}s)")
                return data
            else:
                logger.debug(f"Cache MISS: {key} (expired)")
        return None
    
    def _set_cache(self, key: str, data: Any):
        """Store data in cache."""
        self.cache[key] = (data, time.time())
        logger.debug(f"Cache SET: {key}")
    
    def _clear_old_cache(self):
        """Remove expired cache entries."""
        now = time.time()
        expired = [k for k, (_, ts) in self.cache.items() if now - ts > self.cache_ttl]
        for key in expired:
            del self.cache[key]
        if expired:
            logger.debug(f"Cleared {len(expired)} expired cache entries")
    
    @abstractmethod
    async def validate(self, question: str, reasoning: str, market: dict) -> dict:
        """
        Validate AI's reasoning against real-time data.
        
        Returns:
            {
                "valid": bool,
                "confidence": float (0-1),
                "warning": str | None,
                "details": dict
            }
        """
        pass
