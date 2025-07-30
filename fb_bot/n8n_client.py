import aiohttp
import asyncio
import logging
from typing import Optional, Dict, Any

from .circuit_breaker import n8n_circuit_breaker, retry_with_backoff, RetryConfig

logger = logging.getLogger(__name__)

async def healthcheck_n8n(webhook_url: str, timeout: int = 10) -> bool:
    """
    Verifica se o n8n está respondendo com circuit breaker.

    Args:
        webhook_url: URL do webhook n8n
        timeout: Timeout em segundos

    Returns:
        True se n8n estiver acessível, False caso contrário
    """

    async def _make_healthcheck():
        test_payload = {
            "prompt": "test",
            "author": "healthcheck", 
            "image_url": "",
            "post_id": "healthcheck"
        }

        connector = aiohttp.TCPConnector(
            limit=5,
            limit_per_host=2,
            ttl_dns_cache=300,
            use_dns_cache=True,
        )

        timeout_config = aiohttp.ClientTimeout(total=timeout)

        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout_config,
            headers={'User-Agent': 'FacebookBot/1.0'}
        ) as session:

            async with session.post(webhook_url, json=test_payload) as response:
                # Aceitar qualquer resposta HTTP como "saudável"
                if response.status < 600:
                    return True
                else:
                    raise Exception(f"HTTP {response.status}")

    try:
        # Use circuit breaker for healthcheck (lighter retry config)
        retry_config = RetryConfig(max_attempts=2, base_delay=1.0, max_delay=5.0)
        return await n8n_circuit_breaker.call(
            retry_with_backoff, _make_healthcheck, retry_config
        )

    except Exception as e:
        logger.debug(f"Healthcheck n8n falhou: {e}")
        return False

async def ask_n8n(webhook_url: str, payload: Dict[str, Any], timeout: int = 30) -> Optional[str]:
    """
    Envia dados para o webhook n8n e recebe resposta da IA com circuit breaker.

    Args:
        webhook_url: URL do webhook n8n
        payload: Dados do post para enviar
        timeout: Timeout em segundos

    Returns:
        Resposta da IA ou None em caso de erro
    """

    async def _make_n8n_request():
        connector = aiohttp.TCPConnector(
            limit=10,
            limit_per_host=5,
            ttl_dns_cache=300,
            use_dns_cache=True,
        )

        timeout_config = aiohttp.ClientTimeout(total=timeout)

        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout_config,
            headers={'User-Agent': 'FacebookBot/1.0'}
        ) as session:

            logger.debug(f"Enviando para n8n: {payload}")

            async with session.post(webhook_url, json=payload) as response:
                if response.status == 200:
                    response_data = await response.json()

                    # Extrair resposta da IA do response
                    ai_response = response_data.get('response', '').strip()

                    if ai_response:
                        logger.info("Resposta recebida da IA via n8n")
                        return ai_response
                    else:
                        logger.warning("n8n retornou resposta vazia")
                        return None

                else:
                    logger.error(f"n8n retornou status {response.status}: {await response.text()}")
                    raise Exception(f"n8n HTTP {response.status}")

    try:
        # Use circuit breaker with retry
        retry_config = RetryConfig(max_attempts=3, base_delay=2.0, max_delay=10.0)
        return await n8n_circuit_breaker.call(
            retry_with_backoff, _make_n8n_request, retry_config
        )

    except Exception as e:
        logger.error(f"n8n call failed after circuit breaker/retry: {e}")
        return None