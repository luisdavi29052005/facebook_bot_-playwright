
import aiohttp
import asyncio
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

async def healthcheck_n8n(webhook_url: str, timeout: int = 10) -> bool:
    """
    Verifica se o webhook do n8n está acessível.
    
    Args:
        webhook_url: URL do webhook
        timeout: Timeout em segundos
        
    Returns:
        True se acessível, False caso contrário
    """
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            # Fazer uma requisição HEAD ou GET simples
            async with session.get(webhook_url) as response:
                # Considerar sucesso se status < 500 (pode retornar 404 se GET não suportado)
                return response.status < 500
                
    except asyncio.TimeoutError:
        logger.warning(f"Timeout ao verificar webhook: {webhook_url}")
        return False
    except Exception as e:
        logger.warning(f"Erro ao verificar webhook {webhook_url}: {e}")
        return False

async def ask_n8n(webhook_url: str, payload: Dict[str, Any], timeout: int = 10) -> Optional[str]:
    """
    Envia dados para o webhook do n8n e retorna a resposta.
    
    Args:
        webhook_url: URL do webhook
        payload: Dados para enviar
        timeout: Timeout em segundos
        
    Returns:
        Resposta da IA ou None se erro
    """
    if not webhook_url or not webhook_url.strip():
        logger.error("URL do webhook não configurada")
        return None

    # Validar payload
    required_fields = ['prompt', 'author', 'post_id']
    for field in required_fields:
        if field not in payload:
            logger.error(f"Campo obrigatório ausente no payload: {field}")
            return None

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.post(
                webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'}
            ) as response:
                
                if response.status == 200:
                    try:
                        data = await response.json()
                        reply = data.get('reply', '').strip()
                        
                        if reply:
                            logger.info(f"Resposta recebida do n8n: {len(reply)} chars")
                            return reply
                        else:
                            logger.warning("n8n retornou resposta vazia")
                            return None
                            
                    except Exception as e:
                        logger.error(f"Erro ao decodificar resposta JSON: {e}")
                        # Tentar como texto
                        text_response = await response.text()
                        if text_response.strip():
                            logger.info("Usando resposta como texto")
                            return text_response.strip()
                        return None
                else:
                    error_text = await response.text()
                    logger.error(f"n8n retornou status {response.status}: {error_text}")
                    return None
                    
    except asyncio.TimeoutError:
        logger.error(f"Timeout ao chamar n8n webhook: {webhook_url}")
        return None
    except Exception as e:
        logger.error(f"Erro ao chamar n8n webhook: {e}")
        return None
