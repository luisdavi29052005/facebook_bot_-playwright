
import pytest
from unittest.mock import patch, AsyncMock
import json
from fb_bot.n8n_client import healthcheck_n8n, ask_n8n

@pytest.mark.asyncio
async def test_healthcheck_n8n_success(mock_aiohttp_session):
    """Testa healthcheck bem-sucedido."""
    with patch('aiohttp.ClientSession', return_value=mock_aiohttp_session):
        result = await healthcheck_n8n("https://n8n.example.com/webhook")
        assert result is True

@pytest.mark.asyncio
async def test_healthcheck_n8n_failure():
    """Testa healthcheck com falha."""
    mock_session = AsyncMock()
    mock_response = AsyncMock()
    mock_response.status = 500
    
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    mock_session.get.return_value.__aenter__.return_value = mock_response
    
    with patch('aiohttp.ClientSession', return_value=mock_session):
        result = await healthcheck_n8n("https://n8n.example.com/webhook")
        assert result is False

@pytest.mark.asyncio
async def test_healthcheck_n8n_timeout():
    """Testa timeout no healthcheck."""
    import asyncio
    
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    mock_session.get.side_effect = asyncio.TimeoutError()
    
    with patch('aiohttp.ClientSession', return_value=mock_session):
        result = await healthcheck_n8n("https://n8n.example.com/webhook")
        assert result is False

@pytest.mark.asyncio
async def test_ask_n8n_success(mock_aiohttp_session):
    """Testa chamada bem-sucedida ao n8n."""
    payload = {
        "prompt": "Texto do post",
        "author": "João Silva",
        "post_id": "123"
    }
    
    with patch('aiohttp.ClientSession', return_value=mock_aiohttp_session):
        result = await ask_n8n("https://n8n.example.com/webhook", payload)
        assert result == "Resposta da IA"

@pytest.mark.asyncio
async def test_ask_n8n_invalid_payload():
    """Testa payload inválido."""
    payload = {
        "prompt": "Texto do post"
        # Faltam campos obrigatórios
    }
    
    result = await ask_n8n("https://n8n.example.com/webhook", payload)
    assert result is None

@pytest.mark.asyncio
async def test_ask_n8n_empty_webhook():
    """Testa webhook URL vazia."""
    payload = {
        "prompt": "Texto do post",
        "author": "João Silva",
        "post_id": "123"
    }
    
    result = await ask_n8n("", payload)
    assert result is None

@pytest.mark.asyncio
async def test_ask_n8n_text_response():
    """Testa resposta como texto quando JSON falha."""
    mock_session = AsyncMock()
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
    mock_response.text.return_value = "Resposta em texto"
    
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    mock_session.post.return_value.__aenter__.return_value = mock_response
    
    payload = {
        "prompt": "Texto do post",
        "author": "João Silva",
        "post_id": "123"
    }
    
    with patch('aiohttp.ClientSession', return_value=mock_session):
        result = await ask_n8n("https://n8n.example.com/webhook", payload)
        assert result == "Resposta em texto"

@pytest.mark.asyncio
async def test_ask_n8n_error_status():
    """Testa resposta com status de erro."""
    mock_session = AsyncMock()
    mock_response = AsyncMock()
    mock_response.status = 400
    mock_response.text.return_value = "Bad Request"
    
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    mock_session.post.return_value.__aenter__.return_value = mock_response
    
    payload = {
        "prompt": "Texto do post",
        "author": "João Silva",
        "post_id": "123"
    }
    
    with patch('aiohttp.ClientSession', return_value=mock_session):
        result = await ask_n8n("https://n8n.example.com/webhook", payload)
        assert result is None

@pytest.mark.asyncio
async def test_ask_n8n_empty_reply():
    """Testa resposta JSON com reply vazio."""
    mock_session = AsyncMock()
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"reply": ""}
    
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    mock_session.post.return_value.__aenter__.return_value = mock_response
    
    payload = {
        "prompt": "Texto do post",
        "author": "João Silva",
        "post_id": "123"
    }
    
    with patch('aiohttp.ClientSession', return_value=mock_session):
        result = await ask_n8n("https://n8n.example.com/webhook", payload)
        assert result is None
