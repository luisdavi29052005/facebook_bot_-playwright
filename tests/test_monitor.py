
import pytest
from unittest.mock import AsyncMock, patch
from fb_bot.monitor import _extract_author, _extract_text, _extract_images

@pytest.mark.asyncio
async def test_extract_author_with_separator(mock_post_element):
    """Testa extração de autor com separador ·."""
    mock_post_element.locator.return_value.count.return_value = 1
    mock_post_element.locator.return_value.nth.return_value.is_visible.return_value = True
    mock_post_element.locator.return_value.nth.return_value.inner_text.return_value = "João Silva · 2h"
    
    result = await _extract_author(mock_post_element)
    assert result == "João Silva"

@pytest.mark.asyncio
async def test_extract_author_without_separator(mock_post_element):
    """Testa extração de autor sem separador."""
    mock_post_element.locator.return_value.count.return_value = 1
    mock_post_element.locator.return_value.nth.return_value.is_visible.return_value = True
    mock_post_element.locator.return_value.nth.return_value.inner_text.return_value = "Maria Santos"
    
    result = await _extract_author(mock_post_element)
    assert result == "Maria Santos"

@pytest.mark.asyncio
async def test_extract_author_invalid_name(mock_post_element):
    """Testa rejeição de nomes inválidos."""
    mock_post_element.locator.return_value.count.return_value = 1
    mock_post_element.locator.return_value.nth.return_value.is_visible.return_value = True
    mock_post_element.locator.return_value.nth.return_value.inner_text.return_value = "2h ago"
    
    result = await _extract_author(mock_post_element)
    assert result == ""

@pytest.mark.asyncio
async def test_extract_author_single_word(mock_post_element):
    """Testa rejeição de nome com uma palavra só."""
    mock_post_element.locator.return_value.count.return_value = 1
    mock_post_element.locator.return_value.nth.return_value.is_visible.return_value = True
    mock_post_element.locator.return_value.nth.return_value.inner_text.return_value = "João"
    
    result = await _extract_author(mock_post_element)
    assert result == ""

@pytest.mark.asyncio
async def test_extract_author_invisible_link(mock_post_element):
    """Testa que links invisíveis são ignorados."""
    mock_post_element.locator.return_value.count.return_value = 1
    mock_post_element.locator.return_value.nth.return_value.is_visible.return_value = False
    
    result = await _extract_author(mock_post_element)
    assert result == ""

@pytest.mark.asyncio
async def test_extract_text_multiple_elements(mock_post_element):
    """Testa extração de texto com múltiplos elementos."""
    # Mock múltiplos elementos de texto
    text_mock = AsyncMock()
    text_mock.count.return_value = 2
    
    elem1 = AsyncMock()
    elem1.is_visible.return_value = True
    elem1.inner_text.return_value = "Primeira linha do post"
    
    elem2 = AsyncMock()
    elem2.is_visible.return_value = True
    elem2.inner_text.return_value = "Segunda linha com mais conteúdo"
    
    text_mock.nth.side_effect = [elem1, elem2]
    mock_post_element.locator.return_value = text_mock
    
    result = await _extract_text(mock_post_element)
    assert "Primeira linha do post" in result
    assert "Segunda linha com mais conteúdo" in result

@pytest.mark.asyncio
async def test_extract_text_filters_ui_elements(mock_post_element):
    """Testa que elementos de UI são filtrados."""
    text_mock = AsyncMock()
    text_mock.count.return_value = 2
    
    elem1 = AsyncMock()
    elem1.is_visible.return_value = True
    elem1.inner_text.return_value = "Conteúdo real do post com informações úteis"
    
    elem2 = AsyncMock()
    elem2.is_visible.return_value = True
    elem2.inner_text.return_value = "Ver mais"  # Deve ser filtrado
    
    text_mock.nth.side_effect = [elem1, elem2]
    mock_post_element.locator.return_value = text_mock
    
    result = await _extract_text(mock_post_element)
    assert "Conteúdo real do post" in result
    assert "Ver mais" not in result

@pytest.mark.asyncio
async def test_extract_images():
    """Testa extração de imagens do post."""
    mock_post = AsyncMock()
    
    # Mock evaluate para retornar URLs de imagem
    mock_post.evaluate.return_value = [
        "https://scontent.facebook.com/v/t1.6435-9/image1.jpg",
        "https://scontent.facebook.com/v/t1.6435-9/image2.jpg"
    ]
    
    result = await _extract_images(mock_post)
    
    assert len(result) == 2
    assert "scontent.facebook.com" in result[0]
    assert "scontent.facebook.com" in result[1]

@pytest.mark.asyncio
async def test_extract_images_filters_invalid():
    """Testa que URLs inválidas são filtradas."""
    mock_post = AsyncMock()
    
    # Mock com URLs mistas (válidas e inválidas)
    mock_post.evaluate.return_value = [
        "https://scontent.facebook.com/image.jpg",  # Válida
        "data:image/gif;base64,R0lGOD...",  # Inválida (data URI)
        "",  # Vazia
        "https://static.facebook.com/placeholder.png"  # Inválida (não scontent)
    ]
    
    result = await _extract_images(mock_post)
    
    assert len(result) == 1
    assert "scontent.facebook.com" in result[0]
