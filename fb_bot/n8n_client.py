import aiohttp
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

async def healthcheck_n8n(webhook_url: str, timeout: int = 10) -> bool:
    """Verifica se o webhook n8n está respondendo."""
    try:
        timeout_config = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=timeout_config) as session:
            async with session.get(webhook_url) as response:
                # n8n pode retornar 200, 404 ou 405 para GET em webhook POST
                return response.status in (200, 404, 405)
    except Exception as e:
        logger.warning(f"Erro ao verificar webhook {webhook_url}: {e}")
        return False

async def ask_n8n(webhook_url: str, payload: dict, timeout: int = 30) -> str:
    """Envia payload para n8n e retorna resposta."""
    try:
        timeout_config = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=timeout_config) as session:
            async with session.post(webhook_url, json=payload) as response:

                if response.status == 200:
                    try:
                        data = await response.json(content_type=None)
                        # Tentar diferentes campos de resposta
                        return data.get('response') or data.get('reply') or str(data)
                    except ValueError:
                        text = await response.text()
                        return text
                else:
                    text = await response.text()
                    logger.error(f"n8n retornou status {response.status}: {text}")
                    return ""

    except Exception as e:
        logger.error(f"Erro ao comunicar com n8n: {e}")
        return ""