"""Summary caching system to avoid redundant API calls."""

import os
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
import shutil


@dataclass
class SummaryResult:
    """Result of summarizing assistant messages."""
    summary: str
    tool_calls: List[str]
    error: Optional[str] = None
    tokens_used: Optional[int] = None


@dataclass
class CacheEntry:
    """Represents a cached summary entry."""
    summary_result: SummaryResult
    cached_at: str
    session_id: str
    content_hash: str
    detail_level: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'summary': self.summary_result.summary,
            'tool_calls': self.summary_result.tool_calls,
            'error': self.summary_result.error,
            'tokens_used': self.summary_result.tokens_used,
            'cached_at': self.cached_at,
            'session_id': self.session_id,
            'content_hash': self.content_hash,
            'detail_level': self.detail_level
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CacheEntry':
        """Create from dictionary loaded from JSON."""
        summary_result = SummaryResult(
            summary=data.get('summary', ''),
            tool_calls=data.get('tool_calls', []),
            error=data.get('error'),
            tokens_used=data.get('tokens_used')
        )
        
        return cls(
            summary_result=summary_result,
            cached_at=data.get('cached_at', ''),
            session_id=data.get('session_id', ''),
            content_hash=data.get('content_hash', ''),
            detail_level=data.get('detail_level', 'normal')
        )


class SummaryCache:
    """Manages caching of AI-generated summaries."""
    
    def __init__(self, cache_dir: Optional[str] = None):
        """Initialize cache with custom or default directory."""
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            # Use environment variable or default to ~/.cache/cc-summarize
            default_cache = Path.home() / '.cache' / 'cc-summarize'
            cache_path = os.getenv('CC_SUMMARIZE_CACHE_DIR', default_cache)
            self.cache_dir = Path(cache_path)
        
        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories for organization
        self.summaries_dir = self.cache_dir / 'summaries'
        self.errors_dir = self.cache_dir / 'errors'
        self.summaries_dir.mkdir(exist_ok=True)
        self.errors_dir.mkdir(exist_ok=True)
    
    def _hash_content(self, content: str) -> str:
        """Create hash of content for cache key."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _get_cache_key(self, session_id: str, content_hash: str, detail_level: str) -> str:
        """Generate cache key for a summary."""
        return f"{session_id}_{content_hash}_{detail_level}"
    
    def _get_cache_path(self, cache_key: str, is_error: bool = False) -> Path:
        """Get file path for cache entry."""
        directory = self.errors_dir if is_error else self.summaries_dir
        return directory / f"{cache_key}.json"
    
    def get_summary(self, session_id: str, content: str, detail_level: str) -> Optional[SummaryResult]:
        """Retrieve cached summary if it exists."""
        content_hash = self._hash_content(content)
        cache_key = self._get_cache_key(session_id, content_hash, detail_level)
        
        # Check both successful summaries and errors
        for is_error in [False, True]:
            cache_path = self._get_cache_path(cache_key, is_error)
            
            if cache_path.exists():
                try:
                    with open(cache_path, 'r') as f:
                        data = json.load(f)
                    
                    entry = CacheEntry.from_dict(data)
                    return entry.summary_result
                    
                except (json.JSONDecodeError, KeyError, IOError):
                    # Remove corrupted cache entry
                    cache_path.unlink(missing_ok=True)
        
        return None
    
    def store_summary(self, session_id: str, content: str, detail_level: str, 
                     result: SummaryResult) -> None:
        """Store summary result in cache."""
        content_hash = self._hash_content(content)
        cache_key = self._get_cache_key(session_id, content_hash, detail_level)
        
        # Determine if this is an error result
        is_error = bool(result.error)
        cache_path = self._get_cache_path(cache_key, is_error)
        
        entry = CacheEntry(
            summary_result=result,
            cached_at=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
            content_hash=content_hash,
            detail_level=detail_level
        )
        
        try:
            with open(cache_path, 'w') as f:
                json.dump(entry.to_dict(), f, indent=2)
        except IOError as e:
            print(f"Warning: Failed to cache summary: {e}")
    
    def clear_cache(self, session_id: Optional[str] = None) -> int:
        """Clear cache entries. If session_id provided, only clear that session."""
        cleared_count = 0
        
        for directory in [self.summaries_dir, self.errors_dir]:
            for cache_file in directory.glob('*.json'):
                should_remove = True
                
                if session_id:
                    # Only remove entries for specific session
                    should_remove = cache_file.name.startswith(f"{session_id}_")
                
                if should_remove:
                    try:
                        cache_file.unlink()
                        cleared_count += 1
                    except IOError:
                        pass

        return cleared_count

    def clear_cache_for_sessions(self, session_ids: List[str]) -> int:
        """Clear cache entries for multiple specific sessions."""
        cleared_count = 0

        for directory in [self.summaries_dir, self.errors_dir]:
            for cache_file in directory.glob('*.json'):
                # Check if this cache file matches any of the session IDs
                for session_id in session_ids:
                    if cache_file.name.startswith(f"{session_id}_"):
                        try:
                            cache_file.unlink()
                            cleared_count += 1
                        except IOError:
                            pass
                        break  # Found match, no need to check other session IDs

        return cleared_count
    
    def clear_all_cache(self) -> int:
        """Clear entire cache directory."""
        cleared_count = 0
        
        if self.cache_dir.exists():
            try:
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                self.summaries_dir.mkdir(exist_ok=True)
                self.errors_dir.mkdir(exist_ok=True)
                cleared_count = 1  # Indicate success
            except OSError:
                pass
        
        return cleared_count
    
    def get_failed_entries(self, session_id: Optional[str] = None) -> List[CacheEntry]:
        """Get all cached error entries for retry."""
        failed_entries = []
        
        for error_file in self.errors_dir.glob('*.json'):
            if session_id and not error_file.name.startswith(f"{session_id}_"):
                continue
            
            try:
                with open(error_file, 'r') as f:
                    data = json.load(f)
                
                entry = CacheEntry.from_dict(data)
                failed_entries.append(entry)
                
            except (json.JSONDecodeError, IOError):
                # Remove corrupted error entry
                error_file.unlink(missing_ok=True)
        
        return failed_entries
    
    def retry_failed_entry(self, entry: CacheEntry, new_result: SummaryResult) -> bool:
        """Replace a failed entry with a successful one."""
        # Remove the old error entry
        old_cache_key = self._get_cache_key(
            entry.session_id, 
            entry.content_hash, 
            entry.detail_level
        )
        old_error_path = self._get_cache_path(old_cache_key, is_error=True)
        old_error_path.unlink(missing_ok=True)
        
        # Store the new result
        # We don't have the original content, so we'll use the hash
        fake_content = f"content_hash_{entry.content_hash}"
        self.store_summary(
            entry.session_id,
            fake_content, 
            entry.detail_level,
            new_result
        )
        
        return True
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get statistics about cache usage."""
        return {
            'successful_summaries': len(list(self.summaries_dir.glob('*.json'))),
            'failed_summaries': len(list(self.errors_dir.glob('*.json'))),
            'total_size_bytes': sum(
                f.stat().st_size 
                for f in self.cache_dir.rglob('*.json')
            )
        }