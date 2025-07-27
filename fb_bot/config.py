
import os
import json
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# URLs e configurações básicas
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")
FACEBOOK_GROUP_URL = os.getenv("FACEBOOK_GROUP_URL", "")
FB_GROUP_URL = FACEBOOK_GROUP_URL  # Alias para compatibilidade

# Configurações do navegador
HEADLESS = os.getenv("HEADLESS", "true").lower() in ("true", "1", "t", "yes")
COOKIES_PATH = os.getenv("COOKIES_PATH", "./cookies.json")

# Configurações do loop
LOOP_INTERVAL_SECONDS = int(os.getenv("LOOP_INTERVAL_SECONDS", "60"))

# Palavras-chave para filtrar posts
keywords_env = os.getenv("KEYWORDS", "[]")
try:
    if keywords_env.startswith("[") and keywords_env.endswith("]"):
        KEYWORDS = json.loads(keywords_env)
    else:
        # Se não for JSON, dividir por vírgula
        KEYWORDS = [k.strip() for k in keywords_env.split(",") if k.strip()]
except (json.JSONDecodeError, ValueError):
    # Fallback para lista vazia se houver erro
    KEYWORDS = []

# Validações
if not N8N_WEBHOOK_URL:
    print("⚠️ AVISO: N8N_WEBHOOK_URL não configurado no arquivo .env")

if not FACEBOOK_GROUP_URL:
    print("⚠️ AVISO: FACEBOOK_GROUP_URL não configurado no arquivo .env")

if not KEYWORDS:
    print("⚠️ AVISO: Nenhuma palavra-chave configurada. O bot não filtrará posts.")
    KEYWORDS = []  # Garantir que seja uma lista vazia

# Log das configurações carregadas
print(f"🔧 Configurações carregadas:")
print(f"   N8N_WEBHOOK_URL: {'✅ Configurado' if N8N_WEBHOOK_URL else '❌ Não configurado'}")
print(f"   FACEBOOK_GROUP_URL: {'✅ Configurado' if FACEBOOK_GROUP_URL else '❌ Não configurado'}")
print(f"   HEADLESS: {HEADLESS}")
print(f"   LOOP_INTERVAL_SECONDS: {LOOP_INTERVAL_SECONDS}")
print(f"   KEYWORDS: {KEYWORDS}")
