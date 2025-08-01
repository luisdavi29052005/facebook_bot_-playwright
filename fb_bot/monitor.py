import re
import asyncio
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from playwright.async_api import Page, Locator

from logger import bot_logger
from .selectors import FacebookSelectors
from .viewport_config import (
    setup_optimal_viewport, 
    ensure_element_visible, 
    optimize_page_for_extraction, 
    wait_for_page_stability
)

# Configurar logging para este módulo
logger = logging.getLogger(__name__)

async def navigate_to_group(page: Page, group_url: str):
    """Navega para um grupo do Facebook com retry robusta."""
    bot_logger.info(f"🌍 Navegando para grupo: {group_url}")

    # Configurar viewport otimizado antes da navegação
    await setup_optimal_viewport(page, "desktop_hd")

    # Retry com fallback
    for attempt in range(3):
        try:
            bot_logger.info(f"Tentativa {attempt + 1}/3 de navegação")
            await asyncio.sleep(2 + attempt)

            response = await page.goto(group_url, wait_until='domcontentloaded', timeout=45000)

            if response and response.status >= 400:
                raise Exception(f"Status HTTP {response.status}")

            # Aguardar estabilidade da página
            await wait_for_page_stability(page)

            # Otimizar página para extração
            await optimize_page_for_extraction(page)

            # Verificar se carregou
            feed_found = False
            for indicator in ["div[role='feed']", "div[role='main']", "article[role='article']"]:
                try:
                    await page.wait_for_selector(indicator, state="attached", timeout=8000)
                    feed_found = True
                    break
                except Exception:
                    continue

            if feed_found or attempt == 2:
                # Rolar para ativar carregamento
                await page.mouse.wheel(0, 1000)
                await asyncio.sleep(2)
                bot_logger.success("✅ Grupo carregado com sucesso")
                return
            else:
                raise Exception("Feed não carregou")

        except Exception as e:
            bot_logger.warning(f"Erro na tentativa {attempt + 1}: {e}")
            if attempt < 2:
                await asyncio.sleep(8)
            else:
                bot_logger.warning("Aceitando navegação com falha - tentando continuar")

async def find_next_valid_post(page: Page) -> Optional[Locator]:
    """Encontra o próximo post válido usando os seletores do FacebookSelectors."""
    bot_logger.debug("🔍 Buscando próximo post válido...")

    # Verificar estado da página
    if page.is_closed():
        bot_logger.warning("Página fechada - cancelando busca")
        return None

    # Aguardar estabilidade da página antes de buscar posts
    try:
        await wait_for_page_stability(page, timeout=10000)
        bot_logger.debug("Página estabilizada, iniciando busca de posts")
    except Exception as e:
        bot_logger.warning(f"Erro ao aguardar estabilidade: {e}")
        if page.is_closed():
            return None

    # Usar seletores do FacebookSelectors
    post_selectors = FacebookSelectors.get_post_containers()

    for attempt in range(5):
        # Verificar estado da página a cada tentativa
        if page.is_closed():
            bot_logger.warning("Página fechada durante busca - cancelando")
            return None

        if attempt > 0:
            scroll_distance = 800 + (attempt * 400)
            bot_logger.debug(f"📜 Tentativa {attempt + 1} - Rolando {scroll_distance}px...")
            try:
                # Verificar novamente antes de scroll
                if page.is_closed():
                    bot_logger.warning("Página fechada antes do scroll")
                    return None
                    
                await page.mouse.wheel(0, scroll_distance)
                await asyncio.sleep(2)
                await wait_for_page_stability(page, timeout=5000)
            except Exception as e:
                error_msg = str(e)
                if "Target page" in error_msg and "has been closed" in error_msg:
                    bot_logger.warning("Target page fechada durante scroll")
                    return None
                elif "Connection closed" in error_msg:
                    bot_logger.warning("Conexão fechada durante scroll")
                    return None
                else:
                    bot_logger.debug(f"Erro ao rolar: {e}")
                    break

        # Buscar posts com seletores do FacebookSelectors
        for selector_idx, selector in enumerate(post_selectors):
            try:
                bot_logger.debug(f"🔍 Seletor {selector_idx + 1}: {selector}")
                posts = page.locator(selector)
                count = await posts.count()

                if count == 0:
                    continue

                # Verificar posts sequencialmente
                for i in range(min(count, 8)):
                    try:
                        post = posts.nth(i)

                        # Verificar visibilidade básica primeiro
                        if not await post.is_visible():
                            continue

                        # Usar viewport_config para garantir visibilidade completa
                        try:
                            is_visible = await ensure_element_visible(page, post)
                            if not is_visible:
                                bot_logger.debug(f"Post não pôde ser tornado visível")
                                continue
                        except Exception as e:
                            bot_logger.debug(f"Erro ao tornar post visível: {e}")
                            continue

                        # Validação básica de post
                        if await is_valid_post(post):
                            bot_logger.success(f"✅ POST VÁLIDO encontrado!")
                            
                            # Log adicional para debug
                            try:
                                bbox = await post.bounding_box()
                                bot_logger.debug(f"Post encontrado na posição: {bbox}")
                            except Exception:
                                pass
                            
                            return post

                    except Exception as e:
                        bot_logger.debug(f"Erro verificando post {i}: {e}")
                        continue

            except Exception as e:
                bot_logger.debug(f"Erro com seletor {selector}: {e}")
                continue

    bot_logger.warning("❌ Nenhum post válido encontrado")
    return None

async def is_valid_post(post: Locator) -> bool:
    """Valida se o post é real e não skeleton/UI."""
    try:
        # Verificar se não é skeleton
        skeleton_selectors = [
            '[data-visualcompletion="loading-state"]',
            '[aria-label="Carregando..." i]'
        ]

        for selector in skeleton_selectors:
            try:
                skeleton_elements = post.locator(selector)
                count = await skeleton_elements.count()
                if count > 0:
                    for i in range(count):
                        elem = skeleton_elements.nth(i)
                        if await elem.is_visible():
                            return False
            except Exception:
                continue

        # Verificar se tem role=article ou indicadores básicos
        role = await post.get_attribute("role")
        if role == "article":
            return True

        # Verificar indicadores usando seletores do FacebookSelectors
        author_selectors = FacebookSelectors.get_author_selectors()
        for selector in author_selectors[:3]:  # Primeiros 3 seletores
            try:
                if await post.locator(selector).count() > 0:
                    return True
            except Exception:
                continue

        return False

    except Exception:
        return False

async def extract_post_details(post: Locator, n8n_webhook_url: str = "") -> Dict[str, Any]:
    """Extrai detalhes do post - apenas screenshot e n8n."""
    bot_logger.debug("Extraindo detalhes do post")

    # Verificar se é post válido
    if not await is_valid_post(post):
        bot_logger.warning("Post inválido - pulando")
        return {"author": "", "text": "", "image_url": "", "images_extra": [], "has_video": False}

    # Tirar screenshot
    screenshot_path = await take_post_screenshot(post)
    if not screenshot_path:
        bot_logger.error("Falha ao tirar screenshot")
        return {"author": "", "text": "", "image_url": "", "images_extra": [], "has_video": False}

    # Gerar ID único
    post_id = await extract_post_id(post)

    # Processar via n8n
    if n8n_webhook_url:
        bot_logger.info("🤖 Processando post via n8n...")

        from .n8n_client import process_screenshot_with_n8n

        n8n_result = await process_screenshot_with_n8n(n8n_webhook_url, screenshot_path, post_id)

        if n8n_result:
            author = n8n_result.get('author', '')
            text = n8n_result.get('text', '')
            bot_logger.success(f"✅ Post processado - Autor: '{author}', Texto: {len(text)} chars")

            return {
                "author": author.strip(),
                "text": text.strip(),
                "image_url": screenshot_path,
                "images_extra": [],
                "has_video": False
            }
        else:
            bot_logger.warning("⚠️ n8n não conseguiu processar")
    else:
        bot_logger.error("❌ n8n não configurado")

    return {"author": "", "text": "", "image_url": "", "images_extra": [], "has_video": False}

async def take_post_screenshot(post: Locator) -> Optional[str]:
    """Tira screenshot otimizado do post com verificações robustas."""
    try:
        # Verificações iniciais de estado
        if not post or post.page.is_closed():
            bot_logger.error("Post inválido ou página fechada")
            return None

        page = post.page
        bot_logger.debug("📸 Preparando screenshot do post...")

        # Garantir que o post está visível usando viewport_config
        try:
            is_visible = await ensure_element_visible(page, post)
            if not is_visible:
                bot_logger.warning("Post não pôde ser tornado visível para screenshot")
                return None
        except Exception as e:
            bot_logger.warning(f"Erro ao garantir visibilidade para screenshot: {e}")
            return None

        # Timestamp único
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        screenshots_dir = Path("screenshots/posts")
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        # Encontrar container do article
        try:
            if await post.get_attribute("role") == "article":
                screenshot_element = post
            else:
                article_handle = await post.evaluate_handle('el => el.closest("[role=\'article\']")')
                if article_handle:
                    screenshot_element = article_handle.as_element()
                else:
                    screenshot_element = post
        except Exception:
            screenshot_element = post

        # Garantir visibilidade usando viewport_config
        is_visible = await ensure_element_visible(page, screenshot_element)
        if not is_visible:
            await screenshot_element.scroll_into_view_if_needed()

        # Aguardar elemento estar visível
        try:
            await screenshot_element.wait_for(state="visible", timeout=5000)
        except Exception:
            pass

        await asyncio.sleep(1)

        # Ocultar comentários via CSS
        try:
            await page.add_style_tag(content="""
                [aria-label*="oment" i], 
                [data-testid*="UFI2Comment"],
                [aria-label*="Escreva um comentário" i],
                [aria-label*="Write a comment" i] { 
                    display: none !important; 
                }
                [role="article"] {
                    background: white !important;
                    border: 1px solid #e4e6ea !important;
                    margin-bottom: 16px !important;
                }
            """)
        except Exception:
            pass

        await asyncio.sleep(0.3)

        # Tirar screenshot com tratamento robusto de erros
        screenshot_path = screenshots_dir / f"post_{timestamp}.png"

        try:
            # Verificar estado da página antes do screenshot
            if page.is_closed():
                bot_logger.error("Página fechada antes do screenshot")
                return None

            bbox = await screenshot_element.bounding_box()
            if bbox and bbox["width"] > 0 and bbox["height"] > 0:
                await page.screenshot(
                    path=str(screenshot_path),
                    clip={
                        "x": max(0, bbox["x"]),
                        "y": max(0, bbox["y"]), 
                        "width": min(bbox["width"], 1920),
                        "height": min(bbox["height"], 1080)
                    }
                )
            else:
                # Fallback para screenshot do elemento
                await screenshot_element.screenshot(path=str(screenshot_path))
                
        except Exception as screenshot_error:
            bot_logger.warning(f"Primeiro método de screenshot falhou: {screenshot_error}")
            
            # Segunda tentativa com método alternativo
            try:
                if not page.is_closed():
                    await screenshot_element.screenshot(path=str(screenshot_path))
                else:
                    bot_logger.error("Página fechada durante segunda tentativa de screenshot")
                    return None
            except Exception as final_error:
                error_msg = str(final_error)
                if "Target page" in error_msg and "has been closed" in error_msg:
                    bot_logger.error("Target page fechada durante screenshot")
                elif "Connection closed" in error_msg:
                    bot_logger.error("Conexão fechada durante screenshot")
                else:
                    bot_logger.error(f"Erro final no screenshot: {final_error}")
                return None

        # Validar se o arquivo foi criado com sucesso
        if screenshot_path.exists() and screenshot_path.stat().st_size > 0:
            bot_logger.success(f"📸 Screenshot salvo: {screenshot_path}")
            return str(screenshot_path)
        else:
            bot_logger.error("Screenshot não foi salvo corretamente")
            return None

    except Exception as e:
        error_msg = str(e)
        if "Target page" in error_msg and "has been closed" in error_msg:
            bot_logger.error("Target page fechada durante processo de screenshot")
        elif "Connection closed" in error_msg:
            bot_logger.error("Conexão fechada durante processo de screenshot")
        else:
            bot_logger.error(f"Erro geral no screenshot: {e}")
        return None

async def extract_post_id(post_element: Locator) -> str:
    """Extrai ID único do post."""
    try:
        # Tentar extrair de URLs de permalink
        try:
            permalink_links = post_element.locator('a[href*="story_fbid"], a[href*="posts/"], a[href*="permalink/"]')
            count = await permalink_links.count()

            for i in range(min(count, 3)):
                link = permalink_links.nth(i)
                href = await link.get_attribute("href")
                if href:
                    # Extrair ID da URL
                    story_match = re.search(r'story_fbid=(\d+)', href)
                    if story_match:
                        return f"story_{story_match.group(1)}"

                    posts_match = re.search(r'/posts/(\d+)', href)
                    if posts_match:
                        return f"post_{posts_match.group(1)}"

                    permalink_match = re.search(r'permalink/(\d+)', href)
                    if permalink_match:
                        return f"permalink_{permalink_match.group(1)}"
        except Exception:
            pass

        # Fallback: usar timestamp + posição
        try:
            bbox = await post_element.bounding_box()
            position = f"{int(bbox['x'])}_{int(bbox['y'])}" if bbox else "0_0"
            timestamp = int(datetime.now().timestamp())
            return f"fallback_{timestamp}_{position}"
        except Exception:
            pass

        # Último recurso
        timestamp = int(datetime.now().timestamp())
        return f"unknown_{timestamp}"

    except Exception:
        timestamp = int(datetime.now().timestamp())
        return f"error_{timestamp}"

async def find_next_unprocessed_post(page: Page, processed_keys: set) -> Optional[Locator]:
    """Encontra o próximo post não processado."""
    bot_logger.debug(f"🔍 Buscando post não processado... ({len(processed_keys)} já processados)")

    try:
        post_element = await find_next_valid_post(page)
        if not post_element:
            return None

        post_key = await infer_post_key(post_element)

        if post_key in processed_keys:
            bot_logger.debug(f"Post já processado: {post_key[:30]}...")
            return None

        bot_logger.debug(f"✅ Post não processado encontrado: {post_key[:30]}...")
        return post_element

    except Exception as e:
        bot_logger.error(f"Erro ao buscar post não processado: {e}")
        return None

async def infer_post_key(post_element: Locator) -> str:
    """Gera chave única para o post."""
    try:
        post_id = await extract_post_id(post_element)
        if post_id and post_id != "unknown":
            return post_id

        # Criar chave baseada em conteúdo
        text_content = await post_element.text_content() or ""

        words = []
        for word in text_content.split():
            if len(word) > 3 and word.isalpha():
                words.append(word.lower())
            if len(words) >= 5:
                break

        try:
            bbox = await post_element.bounding_box()
            position = f"{int(bbox['x'])}_{int(bbox['y'])}" if bbox else "0_0"
        except Exception:
            position = "0_0"

        content_key = "_".join(words) if words else "no_text"
        unique_string = f"{content_key}_{position}_{len(text_content)}"

        post_hash = hashlib.md5(unique_string.encode("utf-8", errors="ignore")).hexdigest()[:16]
        return f"inferred:{post_hash}"

    except Exception:
        timestamp = int(datetime.now().timestamp())
        return f"fallback_{timestamp}"

# Função para compatibilidade com o código existente
async def process_post(post: Locator, n8n_webhook_url: str) -> Dict[str, Any]:
    """Wrapper para manter compatibilidade."""
    return await extract_post_details(post, n8n_webhook_url)

async def wait_post_ready(post: Locator):
    """Aguarda o post sair do estado de loading/skeleton antes de extrair dados."""
    try:
        # Verificar se a página ainda está ativa
        if post.page.is_closed():
            return

        # Rolar até o post para garantir visibilidade e ativar carregamento
        await post.scroll_into_view_if_needed()
        await asyncio.sleep(1)

        bot_logger.debug("🔄 Aguardando hidratação completa do post...")

        # ETAPA 1: Aguardar skeletons de carregamento sumirem
        skeleton_selectors = [
            '[role="status"][data-visualcompletion="loading-state"]',
            '[data-visualcompletion="loading-state"]',
            '[aria-label="Carregando..." i]',
            '.shimmer',
            '[aria-busy="true"]'
        ]

        max_skeleton_wait = 15  # 15 segundos máximo para skeleton sumir
        skeleton_gone = False

        for attempt in range(max_skeleton_wait):
            skeleton_found = False

            for selector in skeleton_selectors:
                try:
                    skeleton_elements = post.locator(selector)
                    count = await skeleton_elements.count()

                    if count > 0:
                        # Verificar se algum skeleton ainda está visível
                        for i in range(count):
                            elem = skeleton_elements.nth(i)
                            if await elem.is_visible():
                                skeleton_found = True
                                bot_logger.debug(f"⏳ Skeleton ativo encontrado: {selector} (tentativa {attempt + 1})")
                                break

                        if skeleton_found:
                            break

                except Exception:
                    continue

            if not skeleton_found:
                skeleton_gone = True
                bot_logger.debug("✅ Skeletons removidos - post hidratando...")
                break

            await asyncio.sleep(1)

        # ETAPA 2: Aguardar autor aparecer (indicador chave)
        author_ready = False
        max_author_wait = 10

        for attempt in range(max_author_wait):
            try:
                # Verificar se há link de autor com texto válido
                author_links = post.locator('h3 a[role="link"], h2 a[role="link"]')
                count = await author_links.count()

                for i in range(min(count, 3)):  # Verificar primeiros 3 links
                    try:
                        link = author_links.nth(i)
                        if await link.is_visible():
                            text = await link.text_content()
                            if text and len(text.strip()) >= 3:  # Nome tem pelo menos 3 caracteres
                                # Verificar se não é skeleton text (Facebook às vezes coloca texto temporário)
                                text_clean = text.strip()
                                if not text_clean.startswith('•') and not text_clean.startswith('-'):
                                    author_ready = True
                                    bot_logger.debug(f"✅ Autor carregado: '{text_clean[:20]}...'")
                                    break
                    except Exception:
                        continue

                if author_ready:
                    break

                bot_logger.debug(f"⏳ Aguardando autor aparecer (tentativa {attempt + 1})")
                await asyncio.sleep(1)

            except Exception:
                await asyncio.sleep(1)

        # ETAPA 3: Aguardar conteúdo de texto substancial (se houver)
        try:
            text_elements = post.locator('div[dir="auto"]:visible')
            text_count = await text_elements.count()

            if text_count > 0:
                # Aguardar pelo menos algum texto aparecer
                for attempt in range(5):
                    try:
                        full_text = await post.text_content()
                        if full_text and len(full_text.strip()) > 50:  # Texto substancial
                            bot_logger.debug("✅ Conteúdo de texto carregado")
                            break
                        await asyncio.sleep(1)
                    except Exception:
                        await asyncio.sleep(1)
        except Exception:
            pass

        # ETAPA 4: Aguardar imagens reais (se houver)
        try:
            # Verificar se há imagens e se são reais (não placeholders)
            images = post.locator('img')
            img_count = await images.count()

            if img_count > 0:
                real_images_found = False
                for attempt in range(5):
                    try:
                        for i in range(min(img_count, 3)):
                            img = images.nth(i)
                            if await img.is_visible():
                                src = await img.get_attribute('src')
                                if src and ('scontent' in src or 'fbcdn' in src):
                                    real_images_found = True
                                    break

                        if real_images_found:
                            bot_logger.debug("✅ Imagens reais carregadas")
                            break

                        await asyncio.sleep(1)
                    except Exception:
                        await asyncio.sleep(1)
        except Exception:
            pass

        # ETAPA 5: Delay final para garantir renderização CSS completa
        await asyncio.sleep(2)

        # Verificação final: se ainda há skeleton visível, aguardar mais um pouco
        try:
            final_skeleton_check = post.locator('[data-visualcompletion="loading-state"]:visible')
            if await final_skeleton_check.count() > 0:
                bot_logger.debug("⚠️ Skeleton ainda presente - aguardando mais 3s...")
                await asyncio.sleep(3)
        except Exception:
            pass

        bot_logger.debug("✅ Post completamente hidratado - pronto para extração")

    except Exception as e:
        bot_logger.debug(f"⚠️ Erro aguardando post pronto: {e}")
        # Fallback: aguardar pelo menos um tempo mínimo
        await asyncio.sleep(3)

async def _has_valid_timestamp(article) -> bool:
    """Verifica se o artigo tem um timestamp válido de post."""
    try:
        # Seletores para timestamps
        timestamp_selectors = [
            "time[datetime]",
            "a[href*='story_fbid'] span",
            "span[class*='timestamp']",
            "[data-tooltip-content*='ago'], [data-tooltip-content*='há']",
            "span:has-text('min'), span:has-text('h'), span:has-text('d')",
            "span:regex('^\\d+\\s*(min|h|d|hora|horas|minuto|minutos|dia|dias)$')",
            "a[href*='/posts/'] span",
            "a[href*='/permalink/'] span"
        ]

        for selector in timestamp_selectors:
            try:
                timestamp_elem = article.locator(selector).first()
                if await timestamp_elem.count() > 0 and await timestamp_elem.is_visible():
                    text = await timestamp_elem.text_content()
                    if text and text.strip():
                        # Verificar se o texto parece um timestamp
                        text_lower = text.strip().lower()
                        timestamp_patterns = [
                            r'\d+\s*(min|minuto|minutos|m)(?:$|\s)',
                            r'\d+\s*(h|hora|horas|hr)(?:$|\s)',
                            r'\d+\s*(d|dia|dias|day|days)(?:$|\s)',
                            r'\d+\s*(s|sec|segundo|segundos)(?:$|\s)',
                            r'\d+\s*de\s+(janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)',
                            r'(há|ago)\s+\d+',
                            r'\d{1,2}:\d{2}',  # Horário
                            r'\d{1,2}/\d{1,2}/\d{2,4}'  # Data
                        ]

                        if any(re.search(pattern, text_lower) for pattern in timestamp_patterns):
                            return True
            except Exception:
                continue

        return False

    except Exception:
        return False

async def _has_valid_author_link(article) -> bool:
    """Verifica se o artigo tem um link de autor válido."""
    try:
        # Seletores para links de perfil
        author_link_selectors = [
            "a[href*='/user/']",
            "a[href*='/profile.php']", 
            "a[href*='/people/']",
            "a[href*='facebook.com/'][role='link']"
        ]

        for selector in author_link_selectors:
            try:
                link_elem = article.locator(selector).first()
                if await link_elem.count() > 0 and await link_elem.is_visible():
                    href = await link_elem.get_attribute("href")
                    if href and href.strip():
                        # Verificar se não é link de ação (curtir, comentar, etc.)
                        href_lower = href.lower()
                        if not any(action in href_lower for action in [
                            '/like', '/comment', '/share', '/react',
                            'ufi', 'reaction', 'like.php'
                        ]):
                            # Verificar se tem texto do autor
                            text = await link_elem.text_content()
                            if text and len(text.strip()) >= 2:
                                return True
            except Exception:
                continue

        return False

    except Exception:
        return False

async def _is_ui_element(article) -> bool:
    """Verifica se o elemento é parte da interface do Facebook, não um post."""
    try:
        # Obter todo o texto do elemento
        full_text = await article.text_content()
        if not full_text:
            return True

        text_lower = full_text.lower()

        # Palavras-chave que indicam elementos de UI
        ui_keywords = [
            # Interface do Facebook
            'em destaque', 'featured', 'destacado',
            'próximos eventos', 'upcoming events', 'eventos',
            'acontecendo agora', 'happening now',
            'escreva algo', 'write something', 'what\'s on your mind',
            'no que você está pensando', 'o que você está pensando',

            # Criação de conteúdo
            'criar publicação', 'create post', 'make post',
            'adicionar foto', 'add photo', 'upload photo',
            'adicionar vídeo', 'add video', 'upload video',
            'transmitir ao vivo', 'go live', 'live video',
            'criar enquete', 'create poll',

            # Navegação e menus
            'feed', 'timeline', 'linha do tempo',
            'sugestões para você', 'suggestions for you',
            'pessoas que você pode conhecer', 'people you may know',
            'grupos sugeridos', 'suggested groups',
            'patrocinado', 'sponsored', 'anúncio', 'ad',

            # Ações e botões
            'curtir página', 'like page',
            'seguir', 'follow', 'unfollow',
            'participar do grupo', 'join group',
            'convidar amigos', 'invite friends',
            'compartilhar no seu story', 'share to your story',

            # Carregamento e placeholders
            'carregando', 'loading',
            'aguarde', 'please wait',
            'sem posts para mostrar', 'no posts to show',

            # Headers e títulos de seção
            'publicações', 'posts section',
            'atividade recente', 'recent activity',
            'destaques', 'highlights'
        ]

        # Verificar se contém palavras de UI
        for keyword in ui_keywords:
            if keyword in text_lower:
                bot_logger.debug(f"UI element detectado: '{keyword}' encontrado")
                return True

        # Verificar se é muito curto para ser um post real
        if len(full_text.strip()) < 10:
            return True

        # Verificar se contém apenas botões/ações
        action_only_patterns = [
            r'^(curtir|like|comentar|comment|compartilhar|share)$',
            r'^(seguir|follow|participar|join)$',
            r'^\d+\s*(curtida|like|comentário|comment)s?$'
        ]

        for pattern in action_only_patterns:
            if re.match(pattern, text_lower.strip()):
                return True

        return False

    except Exception as e:
        bot_logger.debug(f"Erro ao verificar UI element: {e}")
        return False

async def _has_author_indicator_fast(article) -> bool:
    """Verificação rápida de indicadores de autor."""
    try:
        # Verificar se tem h3 (onde normalmente fica o autor)
        h3_elements = article.locator('h3')
        if await h3_elements.count() > 0:
            # Verificar se o primeiro h3 tem conteúdo de autor
            first_h3 = h3_elements.first()
            text = await first_h3.text_content()
            if text and len(text.strip()) >= 3:
                # Filtrar timestamps e UI
                text_lower = text.lower().strip()
                if not any(ui_term in text_lower for ui_term in [
                    'min', 'hora', 'h', 'd', 'há', 'ago', 'like', 'comment', 'share'
                ]):
                    return True

        # Verificar links de perfil
        profile_links = article.locator('a[role="link"]')
        if await profile_links.count() > 0:
            return True

        return False

    except Exception:
        return False

async def _has_content_indicator_fast(article) -> bool:
    """Verificação rápida de indicadores de conteúdo."""
    try:
        # Verificar se tem texto significativo
        text_content = await article.text_content()
        if text_content and len(text_content.strip()) > 30:
            return True

        # Verificar se tem imagem do Facebook
        images = article.locator('img[src*="scontent"]')
        if await images.count() > 0:
            return True

        # Verificar se tem vídeo
        videos = article.locator('video')
        if await videos.count() > 0:
            return True

        return False

    except Exception:
        return False

async def _has_timestamp_indicator(article) -> bool:
    """Verificação rápida de timestamp (posts reais têm timestamp)."""
    try:
        # Verificar elementos comuns de timestamp
        timestamp_selectors = [
            'time[datetime]',
            'a[href*="story_fbid"]',
            'span:regex("^\\d+\\s*(min|h|d|hora)")'
        ]

        for selector in timestamp_selectors:
            try:
                if await article.locator(selector).count() > 0:
                    return True
            except Exception:
                continue

        return False

    except Exception:
        return False

async def _is_obvious_ui_element(article) -> bool:
    """Verificação rápida de elementos de UI óbvios."""
    try:
        # Pegar apenas primeiros 200
        text_content = await article.text_content()
        if not text_content:
            return False

        text_snippet = text_content[:200].lower()

        # Palavras-chave que identificam UI do Facebook
        ui_keywords = [
            'escreva algo', 'write something', 'what\'s on your mind',
            'no que você está pensando', 'create post', 'criar publicação',
            'sponsored', 'patrocinado', 'publicidade', 'ad',
            'suggested for you', 'sugestões para você',
            'happening now', 'acontecendo agora',
            'join group', 'participar do grupo'
        ]

        # Se encontrar qualquer keyword de UI, rejeitar
        for keyword in ui_keywords:
            if keyword in text_snippet:
                return True

        # Se o texto é muito curto, provavelmente é UI
        if len(text_content.strip()) < 15:
            return True

        return False

    except Exception:
        return False

async def _has_minimum_content(article) -> bool:
    """Verifica se o artigo tem conteúdo mínimo relevante."""
    try:
        # Extrair texto usando seletores de conteúdo
        content_selectors = [
            'div[dir="auto"]:visible',
            '[data-testid="post_message"]',
            'div[data-ad-preview="message"]'
        ]

        all_text = ""
        for selector in content_selectors:
            try:
                elements = article.locator(selector)
                count = await elements.count()
                for i in range(count):
                    elem = elements.nth(i)
                    if await elem.is_visible():
                        text = await elem.text_content()
                        if text:
                            all_text += " " + text.strip()
            except Exception:
                continue

        # Se não encontrou texto específico, usar texto geral
        if not all_text.strip():
            all_text = await article.text_content() or ""

        # Filtrar texto de UI/ações
        lines = all_text.split('\n')
        relevant_lines = []

        for line in lines:
            line_clean = line.strip()
            if len(line_clean) < 5:  # Muito curto
                continue

            line_lower = line_clean.lower()

            # Filtrar linhas de ação/UI
            ui_line_patterns = [
                'curtir', 'comentar', 'compartilhar',
                'like', 'comment', 'share', 'reply',
                'ver mais', 'see more', 'mostrar mais',
                'ver tradução', 'see translation',
                'follow', 'seguir', 'unfollow',
                'min', 'hora', 'day', 'ago', 'há'
            ]

            # Se a linha tem só palavras de UI, pular
            if (len(line_clean) < 20 and 
                any(ui_word in line_lower for ui_word in ui_line_patterns)):
                continue

            # Se a linha tem pelo menos algumas letras, considerar
            if re.search(r'[a-zA-ZÀ-ÿ]', line_clean):
                relevant_lines.append(line_clean)

        # Juntar texto relevante
        relevant_text = ' '.join(relevant_lines).strip()

        # Verificar se tem conteúdo mínimo
        min_length = 20
        return len(relevant_text) >= min_length

    except Exception:
        return False