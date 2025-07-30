import aiohttp
import asyncio
import logging
import base64
from pathlib import Path
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

async def process_screenshot_with_n8n(webhook_url: str, screenshot_path: str, post_id: str, timeout: int = 60) -> Optional[Dict[str, str]]:
    """
    Envia screenshot do post para n8n processar e extrair autor/texto/reply com IA.

    Args:
        webhook_url: URL do webhook n8n
        screenshot_path: Caminho para o arquivo de screenshot
        post_id: ID único do post
        timeout: Timeout em segundos (maior para processamento de imagem)

    Returns:
        Dict com 'author', 'text' e 'reply' extraídos ou None em caso de erro
    """

    async def _make_screenshot_request():
        # Converter screenshot para base64
        try:
            screenshot_file = Path(screenshot_path)
            if not screenshot_file.exists():
                raise Exception(f"Screenshot não encontrado: {screenshot_path}")

            with open(screenshot_file, 'rb') as f:
                image_data = f.read()
                image_base64 = base64.b64encode(image_data).decode('utf-8')

        except Exception as e:
            logger.error(f"Erro ao ler screenshot: {e}")
            raise

        payload = {
            "image_base64": image_base64,
            "post_id": post_id,
            "filename": screenshot_file.name
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

            logger.info(f"Enviando screenshot para n8n: {screenshot_file.name}")

            async with session.post(webhook_url, json=payload) as response:
                if response.status == 200:
                    response_data = await response.json()

                    # Extrair dados processados pela IA (conforme fluxo n8n)
                    author = response_data.get('author', '').strip()
                    text = response_data.get('text', '').strip()
                    reply = response_data.get('reply', '').strip()
                    
                    if author and text and reply:
                        logger.info(f"✅ Screenshot processado - Autor: '{author}', Texto: {len(text)} chars, Reply: {len(reply)} chars")
                        return {
                            'author': author,
                            'text': text,
                            'reply': reply,
                            'processed_by': 'n8n_ai'
                        }
                    else:
                        logger.warning(f"n8n processou mas dados incompletos - autor:{bool(author)}, texto:{bool(text)}, reply:{bool(reply)}")
                        return None

                else:
                    error_text = await response.text()
                    logger.error(f"n8n retornou status {response.status}: {error_text}")
                    raise Exception(f"n8n HTTP {response.status}")

    try:
        # Use circuit breaker with retry (menos tentativas para screenshots grandes)
        retry_config = RetryConfig(max_attempts=2, base_delay=3.0, max_delay=15.0)
        return await n8n_circuit_breaker.call(
            retry_with_backoff, _make_screenshot_request, retry_config
        )

    except Exception as e:
        logger.error(f"Screenshot processing failed after circuit breaker/retry: {e}")
        return None

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