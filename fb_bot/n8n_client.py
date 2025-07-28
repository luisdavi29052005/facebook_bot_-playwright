import requests
import logging
from logger import bot_logger

def healthcheck_n8n(webhook_url: str, timeout: int = 10) -> bool:
    """Verifica se o n8n está acessível."""
    try:
        response = requests.get(webhook_url, timeout=timeout)
        return response.status_code in [200, 404, 405]  # 404/405 também indicam que o serviço está up
    except requests.exceptions.RequestException as e:
        bot_logger.debug(f"N8N health check falhou: {e}")
        return False

def ask_n8n(webhook_url: str, payload: dict, timeout: int = 30) -> str:
    """Envia dados para o n8n e retorna a resposta."""
    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=timeout,
            headers={'Content-Type': 'application/json'}
        )

        if response.status_code == 200:
            try:
                result = response.json()
                if isinstance(result, dict):
                    return result.get('response', result.get('reply', str(result)))
                else:
                    return str(result)
            except Exception:
                return response.text
        else:
            bot_logger.error(f"N8N retornou status {response.status_code}")
            return ""

    except requests.exceptions.Timeout:
        bot_logger.error("N8N timeout (30s)")
        return ""
    except requests.exceptions.RequestException as e:
        bot_logger.error(f"Erro ao comunicar com N8N: {e}")
        return ""