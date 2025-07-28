import os
import json
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import List

# Carregar variáveis de ambiente uma única vez
load_dotenv()

@dataclass
class BotConfig:
    """Configurações centralizadas do bot."""
    n8n_webhook_url: str
    facebook_group_url: str
    headless: bool
    loop_interval_seconds: int
    max_posts_per_cycle: int
    keywords: List[str]
    cookies_path: str = "./cookies.json"

    @classmethod
    def load_from_env(cls) -> 'BotConfig':
        """Carrega configurações do ambiente."""
        # Processar palavras-chave
        keywords_env = os.getenv("KEYWORDS", "[]")
        try:
            if keywords_env.startswith("[") and keywords_env.endswith("]"):
                keywords = json.loads(keywords_env)
            else:
                keywords = [k.strip() for k in keywords_env.split(",") if k.strip()]
        except (json.JSONDecodeError, ValueError):
            keywords = []

        return cls(
            n8n_webhook_url=os.getenv("N8N_WEBHOOK_URL", ""),
            facebook_group_url=os.getenv("FACEBOOK_GROUP_URL", ""),
            headless=os.getenv("HEADLESS", "true").lower() in ("true", "1", "t", "yes"),
            loop_interval_seconds=int(os.getenv("LOOP_INTERVAL_SECONDS", "60")),
            max_posts_per_cycle=int(os.getenv("MAX_POSTS_PER_CYCLE", "15")),
            keywords=keywords
        )

    def is_valid(self) -> tuple[bool, str]:
        """Valida se as configurações estão corretas."""
        if not self.n8n_webhook_url:
            return False, "N8N_WEBHOOK_URL não configurado"
        if not self.facebook_group_url:
            return False, "FACEBOOK_GROUP_URL não configurado"
        if self.loop_interval_seconds < 30:
            return False, "LOOP_INTERVAL_SECONDS deve ser >= 30"
        return True, ""

# Instância global de configuração
config = BotConfig.load_from_env()

# Aliases para compatibilidade
N8N_WEBHOOK_URL = config.n8n_webhook_url
FACEBOOK_GROUP_URL = config.facebook_group_url
FB_GROUP_URL = config.facebook_group_url
HEADLESS = config.headless
LOOP_INTERVAL_SECONDS = config.loop_interval_seconds
KEYWORDS = config.keywords
COOKIES_PATH = config.cookies_path