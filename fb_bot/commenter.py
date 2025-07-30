import asyncio
import logging
from typing import Optional
from playwright.async_api import ElementHandle

from .selectors import FacebookSelectors

logger = logging.getLogger(__name__)

async def open_comment_box(post_element: ElementHandle) -> bool:
    """
    Abre a caixa de comentários do post usando seletores robustos.
    Tenta múltiplos seletores em ordem de prioridade.
    """
    comment_selectors = FacebookSelectors.get_comment_box_selectors()

    for selector in comment_selectors:
        try:
            comment_box = await post_element.query_selector(selector)
            if comment_box:
                # Verificar se está visível
                is_visible = await comment_box.is_visible()
                if is_visible:
                    logger.debug(f"Caixa de comentários encontrada com seletor: {selector}")
                    await comment_box.click()
                    await asyncio.sleep(1)  # Aguardar interface responder
                    return True
                else:
                    logger.debug(f"Caixa encontrada mas não visível: {selector}")
            else:
                logger.debug(f"Caixa não encontrada com seletor: {selector}")

        except Exception as e:
            logger.debug(f"Erro ao tentar seletor {selector}: {e}")
            continue

    logger.warning("Não foi possível encontrar/abrir caixa de comentários")
    return False

async def send_comment(post_element: ElementHandle, comment_text: str) -> bool:
    """
    Envia um comentário no post usando seletores robustos.
    Usa múltiplas estratégias para envio.
    """
    try:
        # Encontrar caixa de comentários usando seletores robustos
        comment_box_selectors = FacebookSelectors.get_comment_box_selectors()

        comment_box = None
        for selector in comment_box_selectors:
            comment_box = await post_element.query_selector(selector)
            if comment_box:
                is_visible = await comment_box.is_visible()
                if is_visible:
                    break

        if not comment_box:
            logger.warning("Caixa de comentários não encontrada para envio")
            return False

        # Digitar comentário
        await comment_box.click()
        await asyncio.sleep(0.5)
        await comment_box.fill(comment_text)
        await asyncio.sleep(1)

        # Tentar enviar com Enter primeiro
        try:
            await comment_box.press('Enter')
            await asyncio.sleep(2)

            # Verificar se comentário foi enviado (caixa ficou vazia)
            content = await comment_box.inner_text()
            if not content.strip():
                logger.info("Comentário enviado com sucesso (Enter)")
                return True

        except Exception as e:
            logger.debug(f"Envio com Enter falhou: {e}")

        # Fallback: tentar botão de envio usando seletores robustos
        submit_selectors = FacebookSelectors.get_comment_submit_selectors()

        for selector in submit_selectors:
            try:
                submit_button = await post_element.query_selector(selector)
                if submit_button:
                    is_visible = await submit_button.is_visible()
                    if is_visible:
                        await submit_button.click()
                        await asyncio.sleep(2)
                        logger.info("Comentário enviado com sucesso (botão)")
                        return True
            except Exception as e:
                logger.debug(f"Erro com botão de envio {selector}: {e}")
                continue

        logger.warning("Não foi possível enviar comentário")
        return False

    except Exception as e:
        logger.error(f"Erro ao enviar comentário: {e}")
        return False