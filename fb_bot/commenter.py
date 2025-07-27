
# fb_bot/commenter.py
import asyncio
import logging
from playwright.async_api import Locator

async def open_comment_box(post_element: Locator):
    """Tenta abrir a caixa de comentários clicando no botão 'Comentar'"""
    
    # Seletores para diferentes layouts
    comment_selectors = [
        "div[aria-label='Comment'], div[aria-label='Comentar']",
        "span:has-text('Comment'), span:has-text('Comentar') >> xpath=parent::div",
        "a[aria-label*='Comment'], a[aria-label*='Comentar']",
        "div[class*='comment'][role='button']",
        "span:has-text('Comment'), span:has-text('Comentar') >> xpath=ancestor::div[@role='button']",
        "div[role='button']:has(span:has-text('Comment')), div[role='button']:has(span:has-text('Comentar'))"
    ]
    
    for selector in comment_selectors:
        try:
            comment_button = post_element.locator(selector).first
            if await comment_button.count() > 0 and await comment_button.is_visible():
                logging.info(f"💬 Clicando no botão de comentário...")
                await comment_button.click()
                await asyncio.sleep(3)  # Aguardar caixa carregar
                return True
        except Exception as e:
            logging.debug(f"Seletor '{selector}' falhou: {e}")
            continue
    
    # Fallback: procurar por texto "Comment" ou "Comentar"
    try:
        comment_texts = post_element.locator("text=Comment, text=Comentar")
        count = await comment_texts.count()
        
        for i in range(count):
            elem = comment_texts.nth(i)
            try:
                if await elem.is_visible():
                    logging.info(f"💬 Tentando clicar em elemento com texto de comentário...")
                    await elem.click()
                    await asyncio.sleep(3)
                    return True
            except Exception:
                continue
    except Exception:
        pass
    
    logging.warning("❌ Não foi possível encontrar ou clicar no botão de comentário.")
    return False

async def send_comment(post_element: Locator, message: str):
    """Envia a mensagem para a caixa de texto do comentário"""
    
    # Seletores para caixa de comentário
    textbox_selectors = [
        "div[role='textbox']",
        "textarea[placeholder*='comment'], textarea[placeholder*='comentar']",
        "div[contenteditable='true']",
        "div[aria-label*='comment'], div[aria-label*='comentar']",
        "div[class*='notranslate'][contenteditable='true']",
        "textarea[class*='textInput']"
    ]
    
    for selector in textbox_selectors:
        try:
            comment_box = post_element.locator(selector).first
            if await comment_box.count() > 0 and await comment_box.is_visible():
                logging.info(f"✍️ Digitando comentário na caixa de texto...")
                
                # Clicar para focar
                await comment_box.click()
                await asyncio.sleep(1)
                
                # Limpar e digitar
                await comment_box.fill(message)
                await asyncio.sleep(2)
                
                # Enviar com Enter
                await comment_box.press('Enter')
                await asyncio.sleep(2)
                
                logging.info(f"✅ Comentário enviado: {message[:50]}...")
                return True
                
        except Exception as e:
            logging.debug(f"Seletor '{selector}' falhou: {e}")
            continue
    
    # Fallback: procurar botão de envio
    try:
        send_selectors = [
            "button[aria-label*='Post'], button[aria-label*='Enviar']",
            "input[type='submit']",
            "button:has-text('Post'), button:has-text('Enviar')"
        ]
        
        for selector in send_selectors:
            try:
                send_button = post_element.locator(selector).first
                if await send_button.count() > 0 and await send_button.is_visible():
                    await send_button.click()
                    await asyncio.sleep(2)
                    logging.info(f"✅ Comentário enviado via botão")
                    return True
            except Exception:
                continue
    except Exception:
        pass
    
    logging.error(f"❌ Falha ao enviar comentário: {message[:50]}...")
    return False
