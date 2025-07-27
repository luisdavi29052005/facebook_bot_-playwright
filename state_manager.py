# state_manager.py
import json
import logging
import os

STATE_FILE = "processed_posts_state.json"

class StateManager:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StateManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._processed_ids = self._load()
            self._initialized = True

    def _load(self):
        if not os.path.exists(STATE_FILE):
            return set()
        try:
            with open(STATE_FILE, 'r') as f:
                ids = json.load(f)
                logging.info(f"Estado carregado. {len(ids)} posts já processados.")
                return set(ids)
        except (json.JSONDecodeError, FileNotFoundError):
            return set()

    def _save(self):
        with open(STATE_FILE, 'w') as f:
            json.dump(list(self._processed_ids), f)

    def add(self, post_id):
        self._processed_ids.add(post_id)
        self._save()

    def has(self, post_id):
        return post_id in self._processed_ids