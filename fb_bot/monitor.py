
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from playwright.async_api import Page, Locator

# Configuração do logger para registrar informações e erros
logger = logging.getLogger(__name__)

# Seletores CSS melhorados para encontrar posts reais
POST_SELECTORS = [
    'div[role="article"]',
    '[data-pagelet*="FeedUnit"]',
    # Evitar seletores muito genéricos que capturam elementos repetitivos
    'div.x1yztbdb.x1n2onr6.xh8yej3.x1ja2u2z',
    # Seletores mais específicos para posts do Facebook
    'div[data-ft]',
    'div[data-store]',
    'div[data-testid="story-subtitle"]'
]

# Seletores para conteúdo principal do post (excluindo comentários)
POST_CONTENT_SELECTORS = [
    '[data-ad-rendering-role="story_message"]',
    '[data-ad-preview="message"]',
    'div[data-ad-comet-preview="message"]',
    '[data-testid="post_message"]',
    'div.xdj266r.x14z9mp.xat24cr.x1lziwak.x1vvkbs.x126k92a',
    # Seletores mais robustos para o conteúdo do post
    'div.html-div.xdj266r.x14z9mp.xat24cr.x1lziwak.xexx8yu.xyri2b.x18d9i69.x1c1uobl',
    'div[data-ad-comet-preview]',
    '[data-testid="story-subtitle"]'
]

# Seletores para texto dentro do post
TEXT_SELECTORS = [
    '[data-ad-rendering-role="story_message"] span',
    '[data-ad-preview="message"] span',
    'div[data-ad-comet-preview="message"] span',
    'span[dir="auto"]',
    '[data-testid="post_message"] span',
    'div.xdj266r.x14z9mp.xat24cr.x1lziwak.x1vvkbs span'
]

# Seletores para autor do post  
AUTHOR_SELECTORS = [
    '[data-ad-rendering-role="profile_name"] span',
    'h2 span.x193iq5w.xeuugli',
    'h3 a[role="link"] span',
    'strong[data-testid="post_author_name"]',
    'a[data-testid="post_author_link"] span',
    'span.xi81zsa'
]

async def find_next_post(page: Page) -> Optional[Locator]:
    """
    Encontra o próximo post visível na página, evitando elementos repetitivos.
    """
    for attempt in range(3):
        for selector in POST_SELECTORS:
            try:
                posts = page.locator(selector)
                count = await posts.count()
                
                for i in range(min(count, 15)):
                    post = posts.nth(i)
                    try:
                        if await post.is_visible():
                            # Verificar se já foi processado
                            processed_marker = await post.get_attribute("data-processed")
                            if processed_marker == "true":
                                continue
                            
                            # Verificar se tem conteúdo real do post
                            has_main_content = False
                            for content_selector in POST_CONTENT_SELECTORS:
                                try:
                                    content_element = post.locator(content_selector)
                                    if await content_element.count() > 0:
                                        has_main_content = True
                                        break
                                except Exception:
                                    continue
                            
                            if not has_main_content:
                                logger.debug(f"Post {i} não tem conteúdo principal, pulando")
                                continue
                            
                            # Verificar se tem conteúdo de texto substancial
                            text_content = await extract_post_text(post)
                            if text_content and len(text_content.strip()) >= 15:
                                # Evitar posts que são apenas elementos repetitivos
                                if ("Facebook" in text_content and len(text_content.strip()) < 50) or \
                                   ("blockquote" in text_content.lower()) or \
                                   (text_content.count("Facebook") > 2):
                                    logger.debug(f"Post {i} parece ser elemento repetitivo, pulando")
                                    continue
                                
                                # Verificar se não é apenas um link ou elemento vazio
                                if len(text_content.replace(" ", "").replace("\n", "")) < 10:
                                    logger.debug(f"Post {i} tem pouco conteúdo, pulando")
                                    continue
                                    
                                logger.debug(f"Post válido encontrado com seletor: {selector}")
                                return post
                    except Exception as e:
                        logger.debug(f"Erro ao verificar post {i}: {e}")
                        continue
                        
            except Exception as e:
                logger.debug(f"Erro com seletor {selector}: {e}")
                continue

        # Scroll e aguarda antes da próxima tentativa
        if attempt < 2:
            try:
                await page.mouse.wheel(0, 800)
                await asyncio.sleep(1.5)
            except Exception:
                pass

    return None

async def extract_post_text(post: Locator) -> str:
    """
    Extrai o texto do post usando múltiplos seletores.
    """
    text_parts = []
    
    for selector in TEXT_SELECTORS:
        try:
            elements = post.locator(selector)
            count = await elements.count()
            
            for i in range(count):
                element = elements.nth(i)
                text = await element.text_content()
                if text and text.strip():
                    text_parts.append(text.strip())
                    
        except Exception as e:
            logger.debug(f"Erro ao extrair texto com seletor {selector}: {e}")
            continue
    
    # Se não encontrou com seletores específicos, tenta texto geral
    if not text_parts:
        try:
            general_text = await post.text_content()
            if general_text:
                text_parts.append(general_text.strip())
        except Exception:
            pass
    
    return ' '.join(text_parts) if text_parts else ""

async def extract_post_author(post: Locator) -> str:
    """
    Extrai o autor do post usando múltiplos seletores.
    """
    for selector in AUTHOR_SELECTORS:
        try:
            author_element = post.locator(selector).first
            if await author_element.count() > 0:
                author = await author_element.text_content()
                if author and author.strip():
                    return author.strip()
        except Exception as e:
            logger.debug(f"Erro ao extrair autor com seletor {selector}: {e}")
            continue
    
    return ""

# ===== Seletores robustos para compor a área "post completo" =====
HEADER_SELECTORS = [
    '[data-ad-rendering-role="profile_name"]',
    'h2[dir="auto"]',
    'h3[dir="auto"]',
    'a[role="link"] span.x1lliihq.x6ikm8r.x10wlt62.xlyipyv'  # fallback
]

MESSAGE_SELECTORS = [
    '[data-ad-rendering-role="story_message"]',
    '[data-ad-preview="message"]',
    'div[data-ad-comet-preview="message"]',
    '[data-testid="post_message"]',
    'div.xdj266r.x14z9mp.xat24cr.x1lziwak.x1vvkbs'
]

# Mídia visual grande dentro do post (foto/vídeo/capa do álbum)
MEDIA_SELECTORS = [
    'img[src*="scontent"]',
    'img[data-visualcompletion="media-vc-image"]',
    'div[role="img"][style*="background-image"]',
    'video',
    'div[data-visualcompletion="ignore-dynamic"] img'  # fallback
]

def _expand_clip(clip: Dict[str, float], margin: int, max_w: int, max_h: int) -> Dict[str, float]:
    x = max(0, clip["x"] - margin)
    y = max(0, clip["y"] - margin)
    w = min(max_w - x, clip["width"] + 2 * margin)
    h = min(max_h - y, clip["height"] + 2 * margin)
    return {"x": x, "y": y, "width": w, "height": h}

async def _first_visible_bbox(loc: Locator) -> Optional[Dict[str, float]]:
    try:
        count = await loc.count()
        for i in range(min(count, 6)):
            el = loc.nth(i)
            if await el.is_visible():
                bbox = await el.bounding_box()
                if bbox and bbox["width"] > 40 and bbox["height"] > 20:
                    return bbox
    except Exception:
        return None
    return None

def _merge_bboxes(bboxes: List[Dict[str, float]]) -> Optional[Dict[str, float]]:
    bboxes = [b for b in bboxes if b]
    if not bboxes:
        return None
    min_x = min(b["x"] for b in bboxes)
    min_y = min(b["y"] for b in bboxes)
    max_x = max(b["x"] + b["width"] for b in bboxes)
    max_y = max(b["y"] + b["height"] for b in bboxes)
    return {"x": min_x, "y": min_y, "width": max_x - min_x, "height": max_y - min_y}

async def take_post_screenshot(post: Locator) -> Optional[str]:
    """
    Captura SEMPRE o post completo (autor + texto + mídia) em um único screenshot.
    Usa a união das bboxes de header, mensagem e mídia. Evita CSS invasivo.
    """
    try:
        page = post.page
        
        # Garante que o post está no viewport e renderizado
        await post.wait_for(state="visible", timeout=8000)
        await post.scroll_into_view_if_needed(timeout=8000)
        await asyncio.sleep(0.8)

        # Localiza subpartes do post
        header_bbox = await _first_visible_bbox(post.locator(",".join(HEADER_SELECTORS)))
        message_bbox = await _first_visible_bbox(post.locator(",".join(MESSAGE_SELECTORS)))
        media_bbox = await _first_visible_bbox(post.locator(",".join(MEDIA_SELECTORS)))

        # Se não achar partes, usa o próprio post
        post_bbox = await post.bounding_box()
        union_bbox = _merge_bboxes([header_bbox, message_bbox, media_bbox, post_bbox])

        if not union_bbox:
            logger.warning("Não foi possível calcular bounding box do post")
            return None

        # Ajusta viewport se necessário para caber o clip
        original_viewport = page.viewport_size or {"width": 1280, "height": 720}
        need_w = int(max(original_viewport["width"], union_bbox["x"] + union_bbox["width"] + 60))
        need_h = int(max(original_viewport["height"], union_bbox["y"] + union_bbox["height"] + 60))
        viewport_changed = False
        if need_w != original_viewport["width"] or need_h != original_viewport["height"]:
            await page.set_viewport_size({"width": need_w, "height": need_h})
            viewport_changed = True
            await asyncio.sleep(0.2)

        # Centraliza o topo do post na tela para garantir que o clip esteja visível
        await page.evaluate("(y) => window.scrollTo(0, Math.max(0, y - 80))", union_bbox["y"])
        await asyncio.sleep(0.3)

        # Recalcula bboxes após o scroll para garantir precisão
        header_bbox = await _first_visible_bbox(post.locator(",".join(HEADER_SELECTORS)))
        message_bbox = await _first_visible_bbox(post.locator(",".join(MESSAGE_SELECTORS)))
        media_bbox = await _first_visible_bbox(post.locator(",".join(MEDIA_SELECTORS)))
        post_bbox = await post.bounding_box()
        union_bbox = _merge_bboxes([header_bbox, message_bbox, media_bbox, post_bbox])
        if not union_bbox:
            logger.warning("Bounding box perdida após scroll")
            return None

        # Recalcula viewport necessário AGORA (depois do scroll)
        viewport = page.viewport_size or {"width": 1280, "height": 720}
        need_w = viewport["width"]
        need_h = viewport["height"]

        # Expande com margem e CLAMPA para caber no viewport; tudo em int
        margin = 16
        x = max(0, int(union_bbox["x"] - margin))
        y = max(0, int(union_bbox["y"] - margin))
        w = int(union_bbox["width"] + 2*margin)
        h = int(union_bbox["height"] + 2*margin)

        # clamp final dentro do viewport
        w = max(1, min(w, need_w - x))
        h = max(1, min(h, need_h - y))

        clip = {"x": x, "y": y, "width": w, "height": h}

        # Caminho do arquivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        screenshot_dir = Path("screenshots/posts")
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"post_{timestamp}.png"

        try:
            # Tira screenshot da página com clip
            await page.screenshot(
                path=str(screenshot_path), 
                clip=clip, 
                timeout=20000
            )

            if screenshot_path.exists() and screenshot_path.stat().st_size > 2000:
                logger.info(f"✅ Screenshot completo bem-sucedido: {screenshot_path}")
                return str(screenshot_path)
            else:
                raise Exception("Arquivo pequeno ou inválido")
        
        except Exception as e:
            logger.debug(f"page.screenshot com clip falhou, tentando post.screenshot: {e}")
            try:
                # Fallback robusto: o Playwright cuida do scroll automaticamente
                await post.screenshot(path=str(screenshot_path), timeout=25000)
                if screenshot_path.exists() and screenshot_path.stat().st_size > 2000:
                    logger.info(f"✅ Screenshot via element.screenshot: {screenshot_path}")
                    return str(screenshot_path)
                else:
                    logger.error("Screenshot muito pequeno ou inválido")
                    return None
            except Exception as e2:
                logger.error(f"Fallback element.screenshot também falhou: {e2}")
                return None
        
        finally:
            # Restaura viewport original se foi alterado
            if viewport_changed and original_viewport:
                try:
                    await page.set_viewport_size(original_viewport)
                except Exception as e:
                    logger.debug(f"Erro ao restaurar viewport: {e}")

    except Exception as e:
        logger.error(f"Erro crítico no take_post_screenshot: {e}")
        return None

async def extract_post_details(post: Locator, n8n_webhook_url: str) -> Optional[Dict[str, Any]]:
    """
    Extrai detalhes completos do post: texto, autor e gera screenshot.
    """
    try:
        # Extrair texto e autor
        text = await extract_post_text(post)
        author = await extract_post_author(post)
        
        logger.info(f"Extraindo post - Autor: {author[:50]}...")
        logger.info(f"Texto: {text[:100]}...")
        
        # Tirar screenshot
        screenshot_path = await take_post_screenshot(post)
        if not screenshot_path:
            logger.warning("Falha ao gerar screenshot do post")
            return None

        # Se não tem webhook configurado, retorna dados básicos
        if not n8n_webhook_url:
            return {
                "author": author,
                "text": text,
                "reply": "",
                "image_url": screenshot_path
            }

        # Processar com n8n
        try:
            from .n8n_client import process_screenshot_with_n8n
            post_id = f"post_{int(datetime.now().timestamp())}"
            
            result = await process_screenshot_with_n8n(n8n_webhook_url, screenshot_path, post_id)
            
            if result:
                return {
                    "author": author or result.get("author", ""),
                    "text": text or result.get("text", ""),
                    "reply": result.get("reply", ""),
                    "image_url": screenshot_path,
                }
            else:
                logger.warning("n8n não retornou dados válidos")
                return None
                
        except Exception as e:
            logger.error(f"Erro ao processar com n8n: {e}")
            return None

    except Exception as e:
        logger.error(f"Erro em extract_post_details: {e}")
        return None

async def navigate_to_group(page: Page, group_url: str) -> bool:
    """
    Navega para o grupo do Facebook.
    """
    try:
        logger.info(f"Navegando para o grupo: {group_url}")
        await page.goto(group_url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)
        
        # Verifica se chegou na página correta
        current_url = page.url
        if "facebook.com" in current_url:
            logger.info("Navegação para o grupo bem-sucedida")
            return True
        else:
            logger.error(f"URL incorreta após navegação: {current_url}")
            return False
            
    except Exception as e:
        logger.error(f"Erro ao navegar para o grupo: {e}")
        return False

async def find_next_valid_post(page: Page, processed_keys: set) -> Optional[Locator]:
    """
    Encontra o próximo post válido que não foi processado.
    """
    max_attempts = 10
    
    for attempt in range(max_attempts):
        post = await find_next_post(page)
        if not post:
            logger.debug(f"Nenhum post encontrado na tentativa {attempt + 1}")
            continue
            
        # Gerar chave única do post
        post_key = await infer_post_key(post)
        if post_key in processed_keys:
            logger.debug(f"Post já processado: {post_key[:30]}...")
            # Marca no DOM e continua
            try:
                await post.evaluate('el => el.setAttribute("data-processed", "true")')
                await page.mouse.wheel(0, 400)
                await asyncio.sleep(1)
            except Exception:
                pass
            continue
            
        logger.info(f"Post válido encontrado: {post_key[:30]}...")
        return post
    
    logger.warning("Não foi possível encontrar posts válidos após múltiplas tentativas")
    return None

async def find_next_unprocessed_post(page: Page, processed_keys: set) -> Optional[Locator]:
    """
    Alias para find_next_valid_post para compatibilidade.
    """
    return await find_next_valid_post(page, processed_keys)

async def infer_post_key(post: Locator) -> str:
    """
    Gera uma chave única para o post baseada no conteúdo e posição.
    """
    try:
        # Extrai texto e autor
        text = await extract_post_text(post)
        author = await extract_post_author(post)
        
        # Pega bounding box para posição única
        bbox = await post.bounding_box()
        position = f"{bbox['x']},{bbox['y']}" if bbox else "0,0"
        
        # Cria chave baseada no hash do conteúdo + posição + primeiro timestamp
        import hashlib
        timestamp = int(datetime.now().timestamp() / 100) * 100  # Arredonda para minutos
        content = f"{author[:50]}|{text[:100]}|{position}|{timestamp}"
        return hashlib.md5(content.encode()).hexdigest()
        
    except Exception as e:
        logger.debug(f"Erro ao gerar chave do post: {e}")
        # Fallback: usar timestamp único
        return f"post_{int(datetime.now().timestamp() * 1000)}"

async def extract_post_id(post: Locator) -> str:
    """
    Extrai ID único do post.
    """
    try:
        # Tenta extrair ID do HTML
        post_id = await post.get_attribute("data-ft")
        if post_id:
            return post_id
            
        # Fallback: usar chave inferida
        return await infer_post_key(post)
        
    except Exception:
        # Último fallback: timestamp
        return f"post_{int(datetime.now().timestamp())}"

# Função de compatibilidade
async def process_post(post: Locator, n8n_webhook_url: str) -> Optional[Dict[str, Any]]:
    """
    Função de compatibilidade - alias para extract_post_details.
    """
    return await extract_post_details(post, n8n_webhook_url)
