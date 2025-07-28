
import os
import json
from typing import List, Tuple
from pathlib import Path

class BotConfig:
    """Configuração do bot com validação."""
    
    def __init__(self):
        self.n8n_webhook_url: str = ""
        self.facebook_group_url: str = ""
        self.keywords: List[str] = []
        self.loop_interval_seconds: int = 60
        self.max_posts_per_cycle: int = 15
        self.headless: bool = True

    @classmethod
    def load_from_env(cls) -> 'BotConfig':
        """Carrega configuração das variáveis de ambiente."""
        # Reload dotenv to ensure latest values
        from dotenv import load_dotenv
        load_dotenv(override=True)
        
        config = cls()
        
        config.n8n_webhook_url = os.getenv('N8N_WEBHOOK_URL', '').strip()
        config.facebook_group_url = os.getenv('FACEBOOK_GROUP_URL', '').strip()
        
        # Fallback para FB_GROUP_URL se FACEBOOK_GROUP_URL não estiver definida
        if not config.facebook_group_url:
            config.facebook_group_url = os.getenv('FB_GROUP_URL', '').strip()
        
        # Carregar keywords
        keywords_str = os.getenv('KEYWORDS', '').strip()
        if keywords_str:
            try:
                # Tentar como JSON primeiro
                config.keywords = json.loads(keywords_str)
                if not isinstance(config.keywords, list):
                    config.keywords = []
            except json.JSONDecodeError:
                # Fallback para string separada por vírgulas
                config.keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
        
        # Interval com validação
        try:
            interval = int(os.getenv('LOOP_INTERVAL_SECONDS', '60'))
            # Validar limites
            if interval < 30:
                interval = 30
            elif interval > 3600:
                interval = 3600
            config.loop_interval_seconds = interval
        except (ValueError, TypeError):
            config.loop_interval_seconds = 60
        
        # Max posts per cycle
        try:
            max_posts = int(os.getenv('MAX_POSTS_PER_CYCLE', '15'))
            if max_posts < 5:
                max_posts = 5
            elif max_posts > 50:
                max_posts = 50
            config.max_posts_per_cycle = max_posts
        except (ValueError, TypeError):
            config.max_posts_per_cycle = 15
        
        # Headless
        headless_str = os.getenv('HEADLESS', 'true').lower()
        config.headless = headless_str in ('true', '1', 'yes', 'on')
        
        return config

    def is_valid(self) -> Tuple[bool, str]:
        """Valida a configuração."""
        if not self.n8n_webhook_url:
            return False, "URL do webhook n8n não configurada"
        
        if not self.facebook_group_url:
            return False, "URL do grupo Facebook não configurada"
        
        if not self.facebook_group_url.startswith(('http://', 'https://')):
            return False, "URL do grupo deve começar com http:// ou https://"
        
        if self.loop_interval_seconds < 30 or self.loop_interval_seconds > 3600:
            return False, "Intervalo deve estar entre 30 e 3600 segundos"
        
        if self.max_posts_per_cycle < 5 or self.max_posts_per_cycle > 50:
            return False, "Max posts por ciclo deve estar entre 5 e 50"
        
        return True, ""

    def __repr__(self) -> str:
        return (f"BotConfig(webhook='{self.n8n_webhook_url[:30]}...', "
                f"group='{self.facebook_group_url[:30]}...', "
                f"keywords={len(self.keywords)}, "
                f"interval={self.loop_interval_seconds}s, "
                f"max_posts={self.max_posts_per_cycle})")

# Instância global da configuração
config = BotConfig.load_from_env()
