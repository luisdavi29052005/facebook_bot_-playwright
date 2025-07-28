
import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
import tempfile
import json

@pytest.fixture
def mock_post_element():
    """Fixture para elemento de post mock."""
    mock = AsyncMock()
    mock.is_visible.return_value = True
    mock.text_content.return_value = "Texto do post de exemplo"
    mock.inner_text.return_value = "Texto do post de exemplo"
    mock.wait_for_selector = AsyncMock()
    mock.locator.return_value = mock
    mock.count.return_value = 1
    mock.nth.return_value = mock
    mock.get_attribute.return_value = "https://facebook.com/user/123"
    return mock

@pytest.fixture
def sample_post_html():
    """HTML realista de post do Facebook."""
    return """
    <div role="article" class="x1yztbdb">
        <div class="post-header">
            <h3>
                <a href="https://facebook.com/user/123" role="link">
                    <span dir="auto">João Silva</span>
                </a>
            </h3>
            <time datetime="2024-01-15T10:30:00">2h</time>
        </div>
        <div class="post-content">
            <div dir="auto">
                Este é um post de exemplo com conteúdo real.
                Tem múltiplas linhas e informações úteis.
            </div>
            <img src="https://scontent.example.com/image.jpg" alt="Imagem do post">
        </div>
        <div class="post-actions">
            <div role="button">Curtir</div>
            <div role="button">Comentar</div>
            <div role="button">Compartilhar</div>
        </div>
    </div>
    """

@pytest.fixture
def temp_state_file(tmp_path):
    """Arquivo temporário para testes de estado."""
    state_file = tmp_path / "test_state.json"
    # Criar com dados iniciais
    initial_data = ["permalink:https://facebook.com/post/123", "hash:abc123"]
    with open(state_file, 'w') as f:
        json.dump(initial_data, f)
    return str(state_file)

@pytest.fixture
def mock_page():
    """Fixture para página mock do Playwright."""
    mock = AsyncMock()
    mock.is_closed.return_value = False
    mock.evaluate.return_value = "Test Page"
    mock.wait_for_selector = AsyncMock()
    mock.locator.return_value = AsyncMock()
    mock.mouse.wheel = AsyncMock()
    return mock

@pytest.fixture
def mock_aiohttp_session():
    """Mock para sessão aiohttp."""
    session_mock = AsyncMock()
    response_mock = AsyncMock()
    response_mock.status = 200
    response_mock.json.return_value = {"reply": "Resposta da IA"}
    response_mock.text.return_value = "OK"
    
    session_mock.__aenter__.return_value = session_mock
    session_mock.__aexit__.return_value = None
    session_mock.get.return_value.__aenter__.return_value = response_mock
    session_mock.post.return_value.__aenter__.return_value = response_mock
    
    return session_mock
