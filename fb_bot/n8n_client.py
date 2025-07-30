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

            # Healthcheck simples com dados mínimos
            form_data = aiohttp.FormData()
            form_data.add_field('test', 'healthcheck')
            
            async with session.post(webhook_url, data=form_data) as response:
                # Aceitar qualquer resposta HTTP como "saudável"
                if response.status < 600:
                    logger.debug(f"Healthcheck n8n OK: status {response.status}")
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
        # Verificar se arquivo existe
        try:
            screenshot_file = Path(screenshot_path)
            if not screenshot_file.exists():
                raise Exception(f"Screenshot não encontrado: {screenshot_path}")

        except Exception as e:
            logger.error(f"Erro ao verificar screenshot: {e}")
            raise

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

            # Enviar imagem como multipart/form-data (formato esperado pelo n8n)
            form_data = aiohttp.FormData()
            
            with open(screenshot_file, 'rb') as f:
                # Ler os dados da imagem
                image_data = f.read()
                
                # Adicionar imagem com headers corretos
                form_data.add_field(
                    'image', 
                    image_data,
                    filename=screenshot_file.name,
                    content_type='image/png'
                )
                form_data.add_field('post_id', post_id)
                form_data.add_field('timestamp', str(int(asyncio.get_event_loop().time())))

            async with session.post(webhook_url, data=form_data) as response:
                    if response.status == 200:
                        try:
                            response_data = await response.json()
                            logger.debug(f"Resposta do n8n: {response_data}")
                            
                            if response_data is None:
                                logger.warning("n8n retornou resposta nula")
                                return None

                            # Extrair dados processados pela IA (conforme fluxo n8n)
                            author = response_data.get('author', '').strip() if response_data else ''
                            text = response_data.get('text', '').strip() if response_data else ''
                            reply = response_data.get('reply', '').strip() if response_data else ''
                            
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

                        except Exception as json_error:
                            logger.error(f"Erro ao processar JSON do n8n: {json_error}")
                            # Tentar ler como texto
                            response_text = await response.text()
                            logger.debug(f"Resposta como texto: {response_text[:200]}...")
                            return None

                    else:
                        error_text = await response.text()
                        logger.error(f"n8n retornou status {response.status}: {error_text}")
                        raise Exception(f"n8n HTTP {response.status}: {error_text}")

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
                    try:
                        response_data = await response.json()
                        
                        if response_data is None:
                            logger.warning("n8n retornou resposta nula")
                            return None

                        # Extrair resposta da IA do response (múltiplos campos possíveis)
                        ai_response = (
                            response_data.get('response', '') or 
                            response_data.get('reply', '') or 
                            response_data.get('text', '') or
                            str(response_data) if isinstance(response_data, str) else ''
                        ).strip()

                        if ai_response:
                            logger.info("Resposta recebida da IA via n8n")
                            return ai_response
                        else:
                            logger.warning(f"n8n retornou resposta vazia: {response_data}")
                            return None

                    except Exception as json_error:
                        logger.error(f"Erro ao processar JSON do n8n: {json_error}")
                        # Tentar ler como texto
                        response_text = await response.text()
                        if response_text.strip():
                            logger.info("Resposta recebida como texto da IA via n8n")
                            return response_text.strip()
                        return None

                else:
                    error_text = await response.text()
                    logger.error(f"n8n retornou status {response.status}: {error_text}")
                    raise Exception(f"n8n HTTP {response.status}: {error_text}")

    try:
        # Use circuit breaker with retry
        retry_config = RetryConfig(max_attempts=3, base_delay=2.0, max_delay=10.0)
        return await n8n_circuit_breaker.call(
            retry_with_backoff, _make_n8n_request, retry_config
        )

    except Exception as e:
        logger.error(f"n8n call failed after circuit breaker/retry: {e}")
        return None