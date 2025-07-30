
"""
Runtime configuration management for adjustable settings.
Allows configuration changes without restart.
"""

import json
import os
import threading
import time
from typing import Dict, Any, Optional
from pathlib import Path

class RuntimeConfig:
    """
    Thread-safe runtime configuration manager.
    Allows settings to be updated without application restart.
    """
    
    def __init__(self, config_file: str = "runtime_config.json"):
        self.config_file = Path(config_file)
        self._config: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._last_modified = 0
        self._default_config = {
            "keywords": ["fix", "restore", "photo", "repair", "enhance"],
            "max_posts_per_cycle": 10,
            "post_processing_delay": 3,
            "comment_delay": 15,
            "cycle_empty_threshold": 3,
            "scroll_distance": 800,
            "scroll_delay": 2,
            "circuit_breaker": {
                "n8n_failure_threshold": 3,
                "n8n_recovery_timeout": 30,
                "facebook_failure_threshold": 5,
                "facebook_recovery_timeout": 60
            },
            "retry": {
                "max_attempts": 3,
                "base_delay": 1.0,
                "max_delay": 60.0,
                "exponential_base": 2.0
            },
            "extraction": {
                "min_text_length": 10,
                "max_extract_retries": 2,
                "extract_retry_delay": 2
            }
        }
        self._load_config()
    
    def _load_config(self):
        """Load configuration from file."""
        with self._lock:
            try:
                if self.config_file.exists():
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        file_config = json.load(f)
                    
                    # Merge with defaults
                    self._config = self._merge_configs(self._default_config.copy(), file_config)
                    self._last_modified = self.config_file.stat().st_mtime
                else:
                    # Use defaults and create file
                    self._config = self._default_config.copy()
                    self._save_config()
                    
            except Exception as e:
                print(f"Error loading config, using defaults: {e}")
                self._config = self._default_config.copy()
    
    def _merge_configs(self, default: Dict, override: Dict) -> Dict:
        """Recursively merge configuration dictionaries."""
        for key, value in override.items():
            if key in default and isinstance(default[key], dict) and isinstance(value, dict):
                default[key] = self._merge_configs(default[key], value)
            else:
                default[key] = value
        return default
    
    def _save_config(self):
        """Save current configuration to file."""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            self._last_modified = time.time()
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot notation key."""
        self._check_reload()
        
        with self._lock:
            keys = key.split('.')
            value = self._config
            
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            
            return value
    
    def set(self, key: str, value: Any, save: bool = True):
        """Set configuration value by dot notation key."""
        with self._lock:
            keys = key.split('.')
            config = self._config
            
            # Navigate to parent
            for k in keys[:-1]:
                if k not in config:
                    config[k] = {}
                config = config[k]
            
            # Set value
            config[keys[-1]] = value
            
            if save:
                self._save_config()
    
    def update(self, updates: Dict[str, Any], save: bool = True):
        """Update multiple configuration values."""
        with self._lock:
            for key, value in updates.items():
                self.set(key, value, save=False)
            
            if save:
                self._save_config()
    
    def _check_reload(self):
        """Check if config file was modified and reload if needed."""
        if not self.config_file.exists():
            return
        
        try:
            current_mtime = self.config_file.stat().st_mtime
            if current_mtime > self._last_modified:
                self._load_config()
        except Exception:
            pass  # Ignore file access errors
    
    def get_keywords(self) -> list:
        """Get current keywords list."""
        return self.get('keywords', [])
    
    def set_keywords(self, keywords: list):
        """Set keywords list."""
        self.set('keywords', keywords)
    
    def get_max_posts_per_cycle(self) -> int:
        """Get max posts per cycle."""
        return self.get('max_posts_per_cycle', 10)
    
    def get_circuit_breaker_config(self, service: str) -> Dict[str, Any]:
        """Get circuit breaker configuration for service."""
        return self.get(f'circuit_breaker.{service}', {})
    
    def get_retry_config(self) -> Dict[str, Any]:
        """Get retry configuration."""
        return self.get('retry', {})
    
    def to_dict(self) -> Dict[str, Any]:
        """Get complete configuration as dictionary."""
        self._check_reload()
        with self._lock:
            return self._config.copy()

# Global runtime config instance
runtime_config = RuntimeConfig()
