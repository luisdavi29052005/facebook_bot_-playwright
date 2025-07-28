import asyncio
import logging
from playwright.async_api import Locator
import re

# This update improves comment functionality, covering modal and inline scenarios.
async def open_comment_box(post_element):
    """
    Abre a caixa de comentários com suporte a modal e inline.
    Tenta múltiplas estratégias para cobrir variações do Facebook.
    """
    try:
        page = post_element.page

        # Estratégia 1: Botões "Comentar/Comment" com aria-label genérico
        comment_selectors = [
            'div[role="button"]:has-text("Comentar")',
            'div[role="button"]:has-text("Comment")',
            'span[role="button"]:has-text("Comentar")',
            'span[role="button"]:has-text("Comment")',
            '[aria-label*="omment" i]',  # Case insensitive
            '[aria-label*="comentar" i]',
            '[data-testid="UFI2CommentAction/link"]',
            '[data-testid*="comment"]'
        ]

        for selector in comment_selectors:
            try:
                comment_button = post_element.locator(selector).first()
                if await comment_button.count() > 0 and await comment_button.is_visible():
                    logging.info(f"💬 Clicando no botão: {selector}")
                    await comment_button.click()
                    await asyncio.sleep(2)

                    # Verificar se abriu modal ou inline
                    modal_opened = await _check_comment_interface_opened(page, post_element)
                    if modal_opened:
                        return True

            except Exception as e:
                logging.debug(f"Erro com seletor {selector}: {e}")
                continue

        # Estratégia 2: Usar get_by_role
        try:
            comment_by_role = post_element.get_by_role("button", name=re.compile(r"Comment|Comentar", re.IGNORECASE))
            if await comment_by_role.count() > 0:
                logging.info("💬 Clicando via get_by_role")
                await comment_by_role.first().click()
                await asyncio.sleep(2)

                modal_opened = await _check_comment_interface_opened(page, post_element)
                if modal_opened:
                    return True

        except Exception as e:
            logging.debug(f"Erro com get_by_role: {e}")

        # Estratégia 3: Procurar caixa já aberta (pode já estar visível)
        if await _check_comment_interface_opened(page, post_element):
            logging.info("💬 Caixa de comentário já está aberta")
            return True

        logging.warning("❌ Não foi possível abrir caixa de comentários")
        return False

    except Exception as e:
        logging.error(f"❌ Erro ao abrir caixa de comentários: {e}")
        return False

async def _check_comment_interface_opened(page, post_element):
    """Verifica se interface de comentário (modal ou inline) foi aberta."""
    try:
        # Verificar modal
        modal_selectors = [
            'div[role="dialog"] div[contenteditable="true"][role="textbox"]',
            'div[role="dialog"] textarea[placeholder*="omment"]',
            'div[role="dialog"] textarea[placeholder*="comentar"]'
        ]

        for selector in modal_selectors:
            try:
                modal_box = page.locator(selector).first()
                if await modal_box.count() > 0 and await modal_box.is_visible():
                    logging.info("🎭 Modal de comentário detectado")
                    return True
            except Exception:
                continue

        # Verificar inline (no próprio post)
        inline_selectors = [
            'div[contenteditable="true"][role="textbox"]',
            'textarea[placeholder*="omment"], textarea[placeholder*="comentar"]',
            '[data-testid="UFI2CommentTextarea"]'
        ]

        for selector in inline_selectors:
            try:
                inline_box = post_element.locator(selector).first()
                if await inline_box.count() > 0 and await inline_box.is_visible():
                    logging.info("📝 Caixa inline de comentário detectada")
                    return True
            except Exception:
                continue

        return False

    except Exception:
        return False

async def send_comment(post_element, comment_text):
    """
    Envia comentário com suporte a modal e inline.
    Tenta diferentes estratégias de envio.
    """
    try:
        page = post_element.page

        # Procurar caixa de texto (modal primeiro, depois inline)
        text_box = await _find_comment_textbox(page, post_element)
        if not text_box:
            logging.warning("❌ Caixa de texto não encontrada")
            return False

        # Focar na caixa
        await text_box.click()
        await asyncio.sleep(0.5)

        # Limpar conteúdo existente
        try:
            await text_box.press("Control+A")  # Selecionar tudo
            await text_box.press("Delete")     # Deletar
            await asyncio.sleep(0.3)
        except Exception:
            pass

        # Detectar captcha antes de digitar
        if await _detect_captcha(page):
            logging.warning("Captcha detectado - pausando comentário")
            return False

        # Digitar comentário
        logging.info(f"Digitando comentário: {comment_text[:50]}...")
        await text_box.type(comment_text, delay=50)  # Delay para parecer mais humano
        await asyncio.sleep(1)

        # Tentar enviar com Enter
        try:
            await text_box.press("Enter")
            await asyncio.sleep(2)

            # Verificar se foi enviado (textbox ficou vazio/oculto)
            if await _check_comment_sent(page, text_box):
                logging.info("✅ Comentário enviado (Enter)")
                return True

        except Exception as e:
            logging.debug(f"Enter falhou: {e}")

        # Fallback: procurar botão "Enviar/Post"
        send_button = await _find_send_button(page, post_element)
        if send_button:
            try:
                await send_button.click()
                await asyncio.sleep(2)

                if await _check_comment_sent(page, text_box):
                    logging.info("✅ Comentário enviado (botão)")
                    return True

            except Exception as e:
                logging.debug(f"Botão enviar falhou: {e}")

        # Se chegou aqui, tentativa final com Ctrl+Enter
        try:
            await text_box.press("Control+Enter")
            await asyncio.sleep(2)

            if await _check_comment_sent(page, text_box):
                logging.info("✅ Comentário enviado (Ctrl+Enter)")
                return True

        except Exception:
            pass

        logging.warning("❌ Todas as tentativas de enviar falharam")
        return False

    except Exception as e:
        logging.error(f"❌ Erro ao enviar comentário: {e}")
        return False

async def _find_comment_textbox(page, post_element):
    """Encontra caixa de texto de comentário (modal ou inline)."""
    try:
        # Prioridade 1: Modal
        modal_selectors = [
            'div[role="dialog"] div[contenteditable="true"][role="textbox"]',
            'div[role="dialog"] textarea[placeholder*="omment"]',
            'div[role="dialog"] textarea[placeholder*="comentar"]'
        ]

        for selector in modal_selectors:
            try:
                textbox = page.locator(selector).first()
                if await textbox.count() > 0 and await textbox.is_visible():
                    logging.info("📝 Usando textbox modal")
                    return textbox
            except Exception:
                continue

        # Prioridade 2: Inline no post
        inline_selectors = [
            'div[contenteditable="true"][role="textbox"]',
            'textarea[placeholder*="omment"], textarea[placeholder*="comentar"]',
            '[data-testid="UFI2CommentTextarea"]',
            'div[data-testid*="comment"] div[contenteditable="true"]'
        ]

        for selector in inline_selectors:
            try:
                textbox = post_element.locator(selector).first()
                if await textbox.count() > 0 and await textbox.is_visible():
                    logging.info("📝 Usando textbox inline")
                    return textbox
            except Exception:
                continue

        return None

    except Exception:
        return None

async def _find_send_button(page, post_element):
    """Encontra botão de enviar comentário."""
    try:
        # Procurar em modal primeiro
        modal_send_selectors = [
            'div[role="dialog"] button:has-text("Post")',
            'div[role="dialog"] button:has-text("Enviar")',
            'div[role="dialog"] [data-testid*="post"], [data-testid*="send"]'
        ]

        for selector in modal_send_selectors:
            try:
                button = page.locator(selector).first()
                if await button.count() > 0 and await button.is_visible():
                    return button
            except Exception:
                continue

        # Procurar inline no post
        inline_send_selectors = [
            'button:has-text("Post")',
            'button:has-text("Enviar")',
            '[data-testid*="post"], [data-testid*="send"]'
        ]

        for selector in inline_send_selectors:
            try:
                button = post_element.locator(selector).first()
                if await button.count() > 0 and await button.is_visible():
                    return button
            except Exception:
                continue

        return None

    except Exception:
        return None

async def _check_comment_sent(page, textbox):
    """Verifica se comentário foi enviado."""
    try:
        # Verificar se textbox ficou vazio
        content = await textbox.text_content() if textbox else ""
        if not content or content.strip() == "":
            return True

        # Verificar se textbox ficou oculto
        if not await textbox.is_visible():
            return True

        # Aguardar um pouco e verificar novamente
        await asyncio.sleep(1)

        final_content = await textbox.text_content() if textbox else ""
        return not final_content or final_content.strip() == ""

    except Exception:
        # Se der erro ao verificar, assumir que foi enviado
        return True

async def _detect_captcha(page) -> bool:
    """Detecta presença de captcha."""
    try:
        captcha_selectors = [
            'iframe[src*="captcha"]',
            'div[class*="captcha"]',
            '[data-testid*="captcha"]'
        ]
        
        for selector in captcha_selectors:
            try:
                element = page.locator(selector).first()
                if await element.count() > 0 and await element.is_visible():
                    return True
            except Exception:
                continue
                
        return False
        
    except Exception:
        return False