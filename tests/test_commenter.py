
import pytest
from unittest.mock import AsyncMock, patch
from fb_bot.commenter import open_comment_box, send_comment, _detect_captcha

@pytest.mark.asyncio
async def test_open_comment_box_with_text():
    """Testa abertura da caixa de comentários via texto do botão."""
    mock_post = AsyncMock()
    mock_page = AsyncMock()
    mock_post.page = mock_page
    
    # Mock botão "Comentar"
    comment_button = AsyncMock()
    comment_button.count.return_value = 1
    comment_button.is_visible.return_value = True
    
    mock_post.locator.return_value.first.return_value = comment_button
    
    # Mock verificação de interface aberta
    textbox = AsyncMock()
    textbox.count.return_value = 1
    textbox.is_visible.return_value = True
    
    mock_page.locator.return_value.first.return_value = textbox
    
    result = await open_comment_box(mock_post)
    
    assert result is True
    comment_button.click.assert_called_once()

@pytest.mark.asyncio
async def test_open_comment_box_with_aria_label():
    """Testa abertura via aria-label."""
    mock_post = AsyncMock()
    mock_page = AsyncMock()
    mock_post.page = mock_page
    
    # Mock primeiro seletor falha, segundo funciona
    mock_post.locator.side_effect = [
        AsyncMock(first=lambda: AsyncMock(count=AsyncMock(return_value=0))),  # Primeiro falha
        AsyncMock(first=lambda: AsyncMock(count=AsyncMock(return_value=1), is_visible=AsyncMock(return_value=True), click=AsyncMock()))  # Segundo funciona
    ]
    
    # Mock interface aberta
    textbox = AsyncMock()
    textbox.count.return_value = 1
    textbox.is_visible.return_value = True
    mock_page.locator.return_value.first.return_value = textbox
    
    result = await open_comment_box(mock_post)
    assert result is True

@pytest.mark.asyncio
async def test_open_comment_box_get_by_role():
    """Testa fallback para get_by_role."""
    mock_post = AsyncMock()
    mock_page = AsyncMock()
    mock_post.page = mock_page
    
    # Mock seletores tradicionais falham
    mock_post.locator.return_value.first.return_value.count.return_value = 0
    
    # Mock get_by_role funciona
    role_button = AsyncMock()
    role_button.count.return_value = 1
    role_button.click = AsyncMock()
    
    mock_post.get_by_role.return_value.first.return_value = role_button
    
    # Mock interface aberta
    textbox = AsyncMock()
    textbox.count.return_value = 1
    textbox.is_visible.return_value = True
    mock_page.locator.return_value.first.return_value = textbox
    
    result = await open_comment_box(mock_post)
    assert result is True

@pytest.mark.asyncio
async def test_send_comment_success():
    """Testa envio de comentário bem-sucedido."""
    mock_post = AsyncMock()
    mock_page = AsyncMock()
    mock_post.page = mock_page
    
    # Mock textbox encontrada
    textbox = AsyncMock()
    textbox.count.return_value = 1
    textbox.is_visible.return_value = True
    textbox.click = AsyncMock()
    textbox.press = AsyncMock()
    textbox.type = AsyncMock()
    textbox.text_content.return_value = ""  # Vazio após envio
    
    mock_page.locator.return_value.first.return_value = textbox
    
    result = await send_comment(mock_post, "Comentário de teste")
    
    assert result is True
    textbox.type.assert_called_once_with("Comentário de teste", delay=50)
    textbox.press.assert_called_with("Enter")

@pytest.mark.asyncio
async def test_send_comment_with_button():
    """Testa envio usando botão quando Enter falha."""
    mock_post = AsyncMock()
    mock_page = AsyncMock()
    mock_post.page = mock_page
    
    # Mock textbox
    textbox = AsyncMock()
    textbox.count.return_value = 1
    textbox.is_visible.return_value = True
    textbox.click = AsyncMock()
    textbox.press = AsyncMock()
    textbox.type = AsyncMock()
    textbox.text_content.side_effect = ["Comentário de teste", ""]  # Texto permanece após Enter, some após botão
    
    # Mock botão enviar
    send_button = AsyncMock()
    send_button.count.return_value = 1
    send_button.is_visible.return_value = True
    send_button.click = AsyncMock()
    
    mock_page.locator.side_effect = [
        AsyncMock(first=lambda: textbox),  # Textbox
        AsyncMock(first=lambda: send_button)  # Send button
    ]
    
    result = await send_comment(mock_post, "Comentário de teste")
    assert result is True

@pytest.mark.asyncio
async def test_detect_captcha_present():
    """Testa detecção de captcha presente."""
    mock_page = AsyncMock()
    
    # Mock captcha presente
    captcha_element = AsyncMock()
    captcha_element.count.return_value = 1
    captcha_element.is_visible.return_value = True
    
    mock_page.locator.return_value.first.return_value = captcha_element
    
    result = await _detect_captcha(mock_page)
    assert result is True

@pytest.mark.asyncio
async def test_detect_captcha_absent():
    """Testa quando não há captcha."""
    mock_page = AsyncMock()
    
    # Mock sem captcha
    mock_page.locator.return_value.first.return_value.count.return_value = 0
    
    result = await _detect_captcha(mock_page)
    assert result is False
