"""
LLM Response Caching Service
Provides persistent caching for LLM responses using SQLite to avoid redundant API calls.

Key Features:
- Hash-based key generation (rule_text + model + prompt + temperature)
- SQLite persistent storage
- LRU eviction policy
- Thread-safe operations
"""

import sqlite3
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime


class LLMCache:
    """Persistent cache for LLM responses."""
    
    def __init__(self, cache_path: Optional[Path] = None, max_entries: int = 1000):
        """
        Initialize LLM cache.
        
        Args:
            cache_path: Path to SQLite database file
            max_entries: Maximum number of cached entries (LRU eviction)
        """
        if cache_path is None:
            cache_dir = Path(__file__).parent.parent / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = cache_dir / "llm_cache.db"
        
        self.cache_path = cache_path
        self.max_entries = max_entries
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database with schema."""
        conn = sqlite3.connect(str(self.cache_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                cache_key TEXT PRIMARY KEY,
                request_hash TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_type TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 1
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_last_accessed 
            ON llm_cache(last_accessed)
        """)
        
        conn.commit()
        conn.close()
    
    def _generate_key(self, rule_text: str, model: str, prompt_type: str, 
                      temperature: float, extra_params: Optional[Dict] = None) -> str:
        """
        Generate cache key from request parameters.
        
        Args:
            rule_text: Input text
            model: LLM model name
            prompt_type: Type of prompt (classification, fol_generation)
            temperature: Temperature parameter
            extra_params: Additional parameters to include in key
        
        Returns:
            64-character hex string
        """
        key_components = {
            "text": rule_text,
            "model": model,
            "prompt_type": prompt_type,
            "temperature": temperature
        }
        
        if extra_params:
            key_components.update(extra_params)
        
        key_string = json.dumps(key_components, sort_keys=True)
        return hashlib.sha256(key_string.encode()).hexdigest()
    
    def get(self, rule_text: str, model: str, prompt_type: str, 
            temperature: float = 0.0, extra_params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Retrieve cached response if it exists.
        
        Returns:
            Cached response dict or None if not found
        """
        cache_key = self._generate_key(rule_text, model, prompt_type, temperature, extra_params)
        
        conn = sqlite3.connect(str(self.cache_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT response_json FROM llm_cache WHERE cache_key = ?
        """, (cache_key,))
        
        result = cursor.fetchone()
        
        if result:
            # Update access tracking
            cursor.execute("""
                UPDATE llm_cache 
                SET last_accessed = CURRENT_TIMESTAMP,
                    access_count = access_count + 1
                WHERE cache_key = ?
            """, (cache_key,))
            conn.commit()
            conn.close()
            
            return json.loads(result[0])
        
        conn.close()
        return None
    
    def set(self, rule_text: str, model: str, prompt_type: str, 
            response: Dict, temperature: float = 0.0, extra_params: Optional[Dict] = None):
        """
        Store LLM response in cache.
        
        Args:
            rule_text: Input text
            model: LLM model name
            prompt_type: Type of prompt
            response: LLM response to cache
            temperature: Temperature parameter
            extra_params: Additional parameters
        """
        cache_key = self._generate_key(rule_text, model, prompt_type, temperature, extra_params)
        request_hash = hashlib.md5(rule_text.encode()).hexdigest()[:16]
        
        conn = sqlite3.connect(str(self.cache_path))
        cursor = conn.cursor()
        
        # Check cache size and evict if needed
        cursor.execute("SELECT COUNT(*) FROM llm_cache")
        count = cursor.fetchone()[0]
        
        if count >= self.max_entries:
            # Evict oldest accessed entries (LRU)
            cursor.execute("""
                DELETE FROM llm_cache 
                WHERE cache_key IN (
                    SELECT cache_key FROM llm_cache 
                    ORDER BY last_accessed ASC 
                    LIMIT 100
                )
            """)
        
        # Insert or replace
        cursor.execute("""
            INSERT OR REPLACE INTO llm_cache 
            (cache_key, request_hash, model, prompt_type, response_json, created_at, last_accessed)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (cache_key, request_hash, model, prompt_type, json.dumps(response)))
        
        conn.commit()
        conn.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        conn = sqlite3.connect(str(self.cache_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*), SUM(access_count) FROM llm_cache")
        count, total_hits = cursor.fetchone()
        
        cursor.execute("""
            SELECT model, COUNT(*) FROM llm_cache GROUP BY model
        """)
        by_model = dict(cursor.fetchall())
        
        cursor.execute("""
            SELECT prompt_type, COUNT(*) FROM llm_cache GROUP BY prompt_type
        """)
        by_type = dict(cursor.fetchall())
        
        conn.close()
        
        return {
            "total_entries": count or 0,
            "total_cache_hits": total_hits or 0,
            "average_reuse": round((total_hits / count) if count else 0, 2),
            "by_model": by_model,
            "by_prompt_type": by_type
        }
    
    def clear(self):
        """Clear all cached entries."""
        conn = sqlite3.connect(str(self.cache_path))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM llm_cache")
        conn.commit()
        conn.close()


def prompt_key(version: str, **extras) -> dict:
    """Build ``extra_params`` dict for cache calls, always including prompt version.

    Usage::

        cache.get(text, model, "classification",
                  extra_params=prompt_key("v3-hints", deontic_strength="strong"))
    """
    return {"prompt_version": version, **extras}


# Global cache instance
_cache_instance = None


def get_cache() -> LLMCache:
    """Get or create global cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = LLMCache()
    return _cache_instance


if __name__ == "__main__":
    # Test the cache
    cache = get_cache()
    
    # Test set/get
    test_response = {"rule_type": "obligation", "confidence": 0.95}
    cache.set(
        rule_text="Students must pay fees",
        model="mistral",
        prompt_type="classification",
        response=test_response
    )
    
    retrieved = cache.get(
        rule_text="Students must pay fees",
        model="mistral",
        prompt_type="classification"
    )
    
    print(f"Cache test: {retrieved}")
    print(f"Stats: {cache.get_stats()}")
