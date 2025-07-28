
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
                
                # Garantir que o elemento está visível na tela
                await comment_button.scroll_into_view_if_needed()
                await asyncio.sleep(1)
                
                # Clicar no botão
                await comment_button.click()
                
                # Aguardar o modal ou caixa carregar completamente
                await asyncio.sleep(5)
                
                # Verificar se um modal foi aberto
                page = post_element.page
                modal_selectors = [
                    "div[role='dialog']",
                    "div[class*='modal']",
                    "div[aria-modal='true']"
                ]
                
                modal_detected = False
                for modal_selector in modal_selectors:
                    try:
                        modal = page.locator(modal_selector).first
                        if await modal.count() > 0 and await modal.is_visible():
                            logging.info("🎭 Modal de comentário detectado")
                            modal_detected = True
                            break
                    except Exception:
                        continue
                
                if modal_detected:
                    # Se modal foi detectado, aguardar mais tempo
                    await asyncio.sleep(3)
                
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
                    await elem.scroll_into_view_if_needed()
                    await asyncio.sleep(1)
                    await elem.click()
                    await asyncio.sleep(5)
                    return True
            except Exception:
                continue
    except Exception:
        pass
    
    logging.warning("❌ Não foi possível encontrar ou clicar no botão de comentário.")
    return False

async def send_comment(post_element: Locator, message: str):
    """Envia a mensagem para a caixa de texto do comentário"""
    
    page = post_element.page
    
    # Aguardar um pouco mais para garantir que o modal está totalmente carregado
    await asyncio.sleep(3)
    
    # Primeiro, tentar parar qualquer scroll que possa estar acontecendo
    try:
        await page.evaluate("window.scrollTo(window.scrollX, window.scrollY)")
        await asyncio.sleep(1)
    except Exception:
        pass
    
    # Seletores específicos para modais e caixas de comentário do Facebook
    textbox_selectors = [
        # Seletores para modal de comentário
        "div[role='dialog'] div[contenteditable='true'][role='textbox']",
        "div[aria-modal='true'] div[contenteditable='true'][role='textbox']",
        
        # Seletores para caixa inline
        "div[contenteditable='true'][role='textbox']",
        "div[contenteditable='true'][data-lexical-editor='true']",
        
        # Seletores com aria-label específicos
        "div[contenteditable='true'][aria-label*='comentar']",
        "div[contenteditable='true'][aria-label*='comment']",
        "div[contenteditable='true'][aria-label*='Write a comment']",
        "div[contenteditable='true'][aria-label*='Escreva um comentário']",
        "div[contenteditable='true'][aria-label*='Responder como']",
        
        # Seletores mais gerais
        "div[role='textbox'][contenteditable='true']",
        "div[contenteditable='true']",
        "textarea[placeholder*='comment']",
        "textarea[placeholder*='comentar']",
        "div[class*='notranslate'][contenteditable='true']",
        "textarea[class*='textInput']"
    ]
    
    # Estratégia 1: Procurar primeiro em modais
    modal_selectors = [
        "div[role='dialog']",
        "div[aria-modal='true']",
        "div[class*='modal']"
    ]
    
    for modal_selector in modal_selectors:
        try:
            modal = page.locator(modal_selector).first
            if await modal.count() > 0 and await modal.is_visible():
                logging.info(f"🎭 Tentando comentar dentro do modal")
                
                # Parar scroll dentro do modal
                try:
                    await page.evaluate("document.querySelector('div[role=\"dialog\"]')?.scrollTo(0, 0)")
                    await asyncio.sleep(1)
                except Exception:
                    pass
                
                for selector in textbox_selectors[:6]:  # Usar apenas seletores de modal
                    try:
                        comment_box = modal.locator(selector.replace("div[role='dialog'] ", "").replace("div[aria-modal='true'] ", "")).first
                        if await comment_box.count() > 0 and await comment_box.is_visible():
                            logging.info(f"✍️ Encontrou caixa no modal com seletor: {selector}")
                            
                            # Focar na caixa
                            await comment_box.click()
                            await asyncio.sleep(2)
                            
                            # Limpar e digitar
                            await comment_box.press('Control+a')
                            await asyncio.sleep(0.5)
                            await comment_box.type(message, delay=50)
                            await asyncio.sleep(3)
                            
                            # Tentar enviar
                            await comment_box.press('Enter')
                            await asyncio.sleep(5)
                            
                            logging.info(f"✅ Comentário enviado no modal: {message[:50]}...")
                            return True
                            
                    except Exception as e:
                        logging.debug(f"Modal seletor '{selector}' falhou: {e}")
                        continue
                        
                # Se não conseguiu no modal, tentar botão de envio no modal
                send_selectors = [
                    "button[aria-label*='Post comment']",
                    "button[aria-label*='Enviar comentário']",
                    "button[aria-label*='Post']",
                    "button[aria-label*='Enviar']",
                    "button:has-text('Post')",
                    "button:has-text('Enviar')"
                ]
                
                for send_selector in send_selectors:
                    try:
                        send_button = modal.locator(send_selector).first
                        if await send_button.count() > 0 and await send_button.is_visible():
                            logging.info(f"📤 Tentando enviar via botão no modal")
                            await send_button.click()
                            await asyncio.sleep(5)
                            logging.info(f"✅ Comentário enviado via botão no modal")
                            return True
                    except Exception:
                        continue
                        
        except Exception:
            continue
    
    # Estratégia 2: Tentar no contexto do post (inline)
    for selector in textbox_selectors:
        try:
            comment_box = post_element.locator(selector).first
            if await comment_box.count() > 0 and await comment_box.is_visible():
                logging.info(f"✍️ Encontrou caixa inline com seletor: {selector}")
                
                # Scroll até a caixa
                await comment_box.scroll_into_view_if_needed()
                await asyncio.sleep(1)
                
                # Focar na caixa
                await comment_box.click()
                await asyncio.sleep(2)
                
                # Limpar e digitar
                await comment_box.press('Control+a')
                await asyncio.sleep(0.5)
                await comment_box.type(message, delay=50)
                await asyncio.sleep(3)
                
                # Tentar enviar
                await comment_box.press('Enter')
                await asyncio.sleep(5)
                
                logging.info(f"✅ Comentário enviado inline: {message[:50]}...")
                return True
                
        except Exception as e:
            logging.debug(f"Inline seletor '{selector}' falhou: {e}")
            continue
    
    # Estratégia 3: Buscar na página inteira
    for selector in textbox_selectors:
        try:
            comment_box = page.locator(selector).first
            if await comment_box.count() > 0 and await comment_box.is_visible():
                logging.info(f"✍️ Encontrou caixa na página com seletor: {selector}")
                
                # Scroll até a caixa
                await comment_box.scroll_into_view_if_needed()
                await asyncio.sleep(1)
                
                # Focar na caixa
                await comment_box.click()
                await asyncio.sleep(2)
                
                # Limpar e digitar
                await comment_box.press('Control+a')
                await asyncio.sleep(0.5)
                await comment_box.type(message, delay=50)
                await asyncio.sleep(3)
                
                # Tentar enviar
                await comment_box.press('Enter')
                await asyncio.sleep(5)
                
                logging.info(f"✅ Comentário enviado na página: {message[:50]}...")
                return True
                
        except Exception as e:
            logging.debug(f"Página seletor '{selector}' falhou: {e}")
            continue
    
    # Estratégia 4: Procurar especificamente por "Responder como"
    try:
        responder_selectors = [
            "div:has-text('Responder como') + div[contenteditable='true']",
            "div:has-text('Responder como') >> xpath=following-sibling::div[contains(@contenteditable, 'true')]",
            "div:has-text('Responder como') >> xpath=..//*[@contenteditable='true']"
        ]
        
        for selector in responder_selectors:
            try:
                comment_box = page.locator(selector).first
                if await comment_box.count() > 0 and await comment_box.is_visible():
                    logging.info(f"✍️ Encontrou caixa 'Responder como' com seletor: {selector}")
                    
                    await comment_box.scroll_into_view_if_needed()
                    await asyncio.sleep(1)
                    await comment_box.click()
                    await asyncio.sleep(2)
                    
                    await comment_box.press('Control+a')
                    await asyncio.sleep(0.5)
                    await comment_box.type(message, delay=50)
                    await asyncio.sleep(3)
                    
                    await comment_box.press('Enter')
                    await asyncio.sleep(5)
                    
                    logging.info(f"✅ Comentário enviado via 'Responder como': {message[:50]}...")
                    return True
                    
            except Exception as e:
                logging.debug(f"'Responder como' seletor '{selector}' falhou: {e}")
                continue
                
    except Exception:
        pass
    
    logging.error(f"❌ Falha ao enviar comentário: {message[:50]}...")
    return False
