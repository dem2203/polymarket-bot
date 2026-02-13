"""
Fact Checker - Fast orchestrator for all validators.

Design:
- Runs ALL validators in parallel (async)
- Returns FASTEST valid result
- Never blocks (always has fallback)
- Tracks validation failures for health monitor
"""

import logging
import asyncio
from typing import Dict, List

from src.data.validators.crypto import CryptoValidator

logger = logging.getLogger("bot.fact_checker")


class FactChecker:
    """Orchestrate all validators for fast fact-checking."""
    
    def __init__(self):
        # Initialize all validators
        self.crypto_validator = CryptoValidator()
        
        # Validation stats (for health monitor)
        self.validations_run = 0
        self.validations_failed = 0
        self.validations_passed = 0
        
    async def validate_reasoning(
        self,
        question: str,
        reasoning: str,
        market: dict
    ) -> dict:
        """
        Validate AI reasoning against real-time data.
        
        Runs all applicable validators in parallel, returns combined result.
        
        Args:
            question: Market question
            reasoning: AI's reasoning
            market: Full market dict (for context)
            
        Returns:
            {
                "valid": bool,
                "confidence": float (0-1),
                "warnings": List[str],
                "details": dict,
                "validator_results": dict
            }
        """
        self.validations_run += 1
        start_time = asyncio.get_event_loop().time()
        
        # Run all validators in parallel
        tasks = [
            self.crypto_validator.validate(question, reasoning, market),
            # Add more validators here as we build them
        ]
        
        try:
            # Wait for all validators (with timeout)
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=5.0  # Max 5 seconds total
            )
        except asyncio.TimeoutError:
            logger.warning("⚠️ Validation timeout - allowing trade")
            return {
                "valid": True,
                "confidence": 0.5,
                "warnings": ["Validation timeout"],
                "details": {},
                "validator_results": {}
            }
        
        # Process results
        all_valid = True
        min_confidence = 1.0
        warnings = []
        all_details = {}
        validator_results = {}
        
        for i, result in enumerate(results):
            # Handle exceptions
            if isinstance(result, Exception):
                logger.warning(f"Validator {i} exception: {result}")
                continue
            
            validator_name = f"validator_{i}"
            validator_results[validator_name] = result
            
            if not result.get("valid", True):
                all_valid = False
                self.validations_failed += 1
                
                if result.get("warning"):
                    warnings.append(result["warning"])
            
            # Track lowest confidence
            conf = result.get("confidence", 1.0)
            if conf < min_confidence:
                min_confidence = conf
            
            # Merge details
            if result.get("details"):
                all_details.update(result["details"])
        
        if all_valid:
            self.validations_passed += 1
        
        # Calculate elapsed time
        elapsed_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        logger.debug(f"✅ Validation complete in {elapsed_ms:.0f}ms")
        
        return {
            "valid": all_valid,
            "confidence": min_confidence,
            "warnings": warnings,
            "details": all_details,
            "validator_results": validator_results,
            "elapsed_ms": elapsed_ms
        }
    
    def get_stats(self) -> dict:
        """Get validation statistics."""
        return {
            "total_validations": self.validations_run,
            "passed": self.validations_passed,
            "failed": self.validations_failed,
            "failure_rate": (
                self.validations_failed / max(self.validations_run, 1)
            )
        }
