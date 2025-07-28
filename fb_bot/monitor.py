import asyncio
import hashlib
import logging
import re
import os
from datetime import datetime
from pathlib import Path
from playwright.async_api import Page, Locator
from logger import bot_logger
from .selectors import (
    FEED, ARTICLE, POST_SELECTORS, AUTHOR_STRATEGIES, TEXT_STRATEGIES, 
    IMAGE_STRATEGIES, AUTHOR_EXCLUDE_PATTERNS, TEXT_EXCLUDE_PATTERNS,
    expand_article_text
)

# Configurar logging para este módulo
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_dump_article(article: Locator, tag: str):
    """
    Salva screenshot e HTML do artigo para debug.
    
    Args:
        article: Elemento do artigo
        tag: Tag para identificar o tipo de problema (missing_author, missing_text, missing_images)
    """
    try:
        # Criar timestamp único
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # microseconds truncados
        
        # Criar diretórios se não existirem
        screenshots_dir = Path("screenshots/articles")
        html_dumps_dir = Path("html_dumps/articles")
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        html_dumps_dir.mkdir(parents=True, exist_ok=True)
        
        # Salvar screenshot
        screenshot_path = screenshots_dir / f"{timestamp}_{tag}.png"
        await article.screenshot(path=str(screenshot_path))
        bot_logger.debug(f"Screenshot salvo: {screenshot_path}")
        
        # Salvar HTML
        html_path = html_dumps_dir / f"{timestamp}_{tag}.html"
        inner_html = await article.inner_html()
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Debug Dump - {tag} - {timestamp}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .debug-info {{ background: #f5f5f5; padding: 10px; border-radius: 5px; margin-bottom: 20px; }}
        .article-content {{ border: 1px solid #ddd; padding: 10px; }}
    </style>
</head>
<body>
    <div class="debug-info">
        <h1>Debug Dump: {tag}</h1>
        <p><strong>Timestamp:</strong> {timestamp}</p>
        <p><strong>Problema:</strong> {tag.replace('_', ' ').title()}</p>
    </div>
    <div class="article-content">
{inner_html}
    </div>
</body>
</html>""")
        
        bot_logger.debug(f"HTML dump salvo: {html_path}")
        
    except Exception as e:
        bot_logger.warning(f"Erro ao criar debug dump: {e}")

async def navigate_to_group(page: Page, group_url: str):
    """Navega para um grupo do Facebook com retry robusta."""
    bot_logger.info(f"Acessando grupo: {group_url}")
    
    # Retry com fallback de load-state
    for attempt in range(3):
        try:
            bot_logger.info(f"Tentativa {attempt + 1}/3 de navegação")
            
            # Navegar com wait_until domcontentloaded
            response = await page.goto(group_url, wait_until='domcontentloaded', timeout=30000)
            
            if response and response.status >= 400:
                raise Exception(f"Status HTTP {response.status}")
            
            # Aguardar rede ficar ociosa
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                bot_logger.debug("Timeout networkidle - continuando")
            
            # Aguardar feed aparecer (attached, não visible)
            try:
                await page.wait_for_selector(FEED, state="attached", timeout=15000)
                bot_logger.debug(f"Feed detectado na tentativa {attempt + 1}")
                
                # Rolar uma vez para ativar o carregamento
                await page.mouse.wheel(0, 800)
                await asyncio.sleep(1)
                
                # Aguardar conteúdo sair do skeleton
                await asyncio.sleep(2)
                
                bot_logger.success("Feed do grupo carregado")
                return
                
            except Exception as e:
                bot_logger.warning(f"Feed não carregou na tentativa {attempt + 1}: {e}")
                if attempt < 2:
                    await asyncio.sleep(3)
                    continue
                else:
                    raise
            
        except Exception as e:
            bot_logger.warning(f"Erro na tentativa {attempt + 1}: {e}")
            if attempt < 2:
                await asyncio.sleep(5)
                continue
            else:
                raise Exception(f"Falha após 3 tentativas: {e}")

async def wait_post_ready(post: Locator):
    """
    Aguarda o post sair do estado de loading/skeleton antes de extrair dados.
    Anti-skeleton robusto para evitar extração prematura.
    
    Args:
        post: Elemento do post
    """
    try:
        # Verificar se a página ainda está ativa
        if post.page.is_closed():
            return
        
        # Rolar até o post para garantir visibilidade
        await post.scroll_into_view_if_needed()
        
        # Aguardar múltiplos tipos de skeleton/loading
        skeleton_selectors = [
            '[role="status"][data-visualcompletion="loading-state"]',
            '[data-visualcompletion="loading-state"]',
            '.shimmer',
            '[aria-busy="true"]',
            '.placeholder',
            '[data-placeholder="1"]'
        ]
        
        for selector in skeleton_selectors:
            try:
                skeleton = post.locator(selector).first()
                if await skeleton.count() > 0:
                    bot_logger.debug(f"Aguardando skeleton sumir: {selector}")
                    await skeleton.wait_for(state='detached', timeout=8000)
            except Exception:
                continue
        
        # Aguardar imagens reais carregarem
        try:
            # Verificar placeholders de imagem
            placeholder_selectors = [
                'img[src*="safe_image"]',
                'img[src*="static"]',
                'img[src=""]'
            ]
            
            for selector in placeholder_selectors:
                placeholder = post.locator(selector).first()
                if await placeholder.count() > 0:
                    bot_logger.debug("Aguardando imagem real carregar...")
                    # Aguardar imagem com conteúdo real
                    await post.wait_for_selector('img[src*="scontent"], img[src*="fbcdn"]', timeout=6000)
                    break
        except Exception:
            pass
        
        # Aguardar conteúdo de texto aparecer (não apenas skeleton)
        try:
            # Verificar se há texto real ou ainda é placeholder
            text_content = await post.text_content()
            if not text_content or len(text_content.strip()) < 10:
                bot_logger.debug("Aguardando conteúdo de texto aparecer...")
                await asyncio.sleep(1.5)
        except Exception:
            pass
        
        # Aguardar rede ficar ociosa (timeout baixo)
        try:
            await post.page.wait_for_load_state("networkidle", timeout=2000)
        except Exception:
            pass
        
        # Delay final para garantir renderização
        await asyncio.sleep(0.8)
        
    except Exception as e:
        bot_logger.debug(f"Erro aguardando post pronto: {e}")

async def iterate_posts(page: Page, max_posts: int = 15, scroll_delay: float = 1.0):
    """
    Itera pelos posts do feed com coleta limitada e detecção de crescimento.
    Para quando não há "ganho" após scrolls para evitar loops infinitos.
    
    Args:
        page: Página do Playwright
        max_posts: Número máximo de posts a processar
        scroll_delay: Delay entre scrolls
        
    Yields:
        Locator: Elementos de posts válidos
    """
    bot_logger.debug(f"Iniciando coleta limitada de posts (máx: {max_posts})")
    
    # Verificar se página ainda está ativa
    if page.is_closed():
        bot_logger.warning("Página fechada - cancelando iteração")
        return
    
    # Garantir que o feed esteja presente
    try:
        await page.wait_for_selector(FEED, state="attached", timeout=10000)
    except Exception:
        bot_logger.warning("Feed não encontrado - cancelando iteração")
        return
    
    # Primeiro, coletar artigos até um mínimo (5-10) com detecção de crescimento
    target_articles = min(max_posts, 10)  # Alvo inicial
    collected_articles = []
    scroll_attempts = 0
    max_scroll_attempts = 8
    last_count = 0
    no_growth_cycles = 0
    
    bot_logger.debug(f"Coletando até {target_articles} artigos...")
    
    while len(collected_articles) < target_articles and scroll_attempts < max_scroll_attempts:
        try:
            # Buscar artigos no feed
            feed_locator = page.locator(FEED)
            articles = feed_locator.locator('article[role="article"], div[data-pagelet^="FeedUnit_"]')
            current_count = await articles.count()
            
            bot_logger.debug(f"Artigos no DOM: {current_count}, coletados: {len(collected_articles)}")
            
            # Processar novos artigos encontrados
            for i in range(len(collected_articles), min(current_count, target_articles)):
                try:
                    article = articles.nth(i)
                    
                    # Verificar se elemento é válido e visível
                    if not await article.is_visible():
                        continue
                    
                    # Aguardar post sair do skeleton
                    await wait_post_ready(article)
                    
                    # Validar conteúdo básico
                    text_content = await article.text_content()
                    if not text_content or len(text_content.strip()) < 20:
                        continue
                    
                    # Filtrar elementos de UI/navegação
                    ui_patterns = [
                        'like', 'comment', 'share', 'curtir', 'comentar', 'compartilhar',
                        'most relevant', 'top contributor', 'follow', 'seguir', 
                        'see all', 'ver tudo', 'show more', 'mostrar mais'
                    ]
                    
                    text_lower = text_content.lower()
                    if (len(text_content) < 80 and 
                        any(pattern in text_lower for pattern in ui_patterns)):
                        continue
                    
                    # Artigo válido - adicionar à coleção
                    collected_articles.append(article)
                    bot_logger.debug(f"Artigo {len(collected_articles)} coletado: {text_content[:40]}...")
                    
                except Exception as e:
                    bot_logger.debug(f"Erro coletando artigo {i}: {e}")
                    continue
            
            # Detecção de crescimento
            if current_count == last_count:
                no_growth_cycles += 1
                bot_logger.debug(f"Sem crescimento - ciclo {no_growth_cycles}")
                
                if no_growth_cycles >= 2:
                    bot_logger.debug("Sem crescimento por 2 ciclos - parando coleta")
                    break
                
                # Rolar para tentar carregar mais
                await page.mouse.wheel(0, 1000)
                await asyncio.sleep(scroll_delay * 1.5)
                scroll_attempts += 1
            else:
                no_growth_cycles = 0
                scroll_attempts = 0  # Reset se houve crescimento
                
            last_count = current_count
            
        except Exception as e:
            bot_logger.warning(f"Erro na coleta: {e}")
            break
    
    bot_logger.info(f"Coleta concluída: {len(collected_articles)} artigos disponíveis")
    
    # Agora iterar pelos artigos coletados
    for i, article in enumerate(collected_articles):
        try:
            # Verificar se página ainda está ativa
            if page.is_closed():
                bot_logger.warning("Página fechada durante iteração")
                break
            
            # Re-aguardar o post estar pronto (pode ter mudado)
            await wait_post_ready(article)
            
            bot_logger.debug(f"Processando artigo {i + 1}/{len(collected_articles)}")
            yield article
            
        except Exception as e:
            bot_logger.debug(f"Erro iterando artigo {i}: {e}")
            continue

async def find_next_valid_post(page: Page, skip_count: int = 0):
    """
    Função mantida para compatibilidade - agora usa iterate_posts internamente.
    """
    bot_logger.debug(f"Buscando post #{skip_count + 1} (método legado)")
    
    count = 0
    async for post in iterate_posts(page, max_posts=skip_count + 5):
        if count == skip_count:
            return post
        count += 1
    
    return None

async def extract_post_id(post_element: Locator):
    """
    Extrai ID único do post usando múltiplas estratégias.
    Corrigido para não depender de funções inexistentes.
    """
    try:
        # Estratégia 1: Links de permalink/timestamp
        link_selectors = [
            "a[href*='/posts/']",
            "a[href*='/permalink/']", 
            "a[href*='/story.php']",
            "a[href*='story_fbid']",
            "time[datetime] a",  # Link no timestamp
            "span[id*='feed_subtitle'] a"  # Link no subtítulo
        ]

        for selector in link_selectors:
            try:
                links = post_element.locator(selector)
                count = await links.count()
                
                for i in range(count):
                    link = links.nth(i)
                    href = await link.get_attribute("href")
                    
                    if href and href.strip():
                        # Limpar URL
                        clean_href = href.split("?")[0].split("#")[0]
                        
                        # Verificar se é permalink válido
                        permalink_patterns = ['/posts/', '/permalink/', 'story_fbid', '/p/']
                        if any(pattern in clean_href for pattern in permalink_patterns):
                            return f"permalink:{clean_href}"
                            
            except Exception:
                continue
                
    except Exception:
        pass

    # Estratégia 2: Atributos de dados únicos
    try:
        data_attrs = [
            'data-ft', 'data-testid', 'id', 'data-story-id',
            'data-pagelet', 'data-tn', 'data-feed-story-id'
        ]
        
        for attr in data_attrs:
            try:
                value = await post_element.get_attribute(attr)
                if value and value.strip() and len(value) > 3:
                    return f"attr:{attr}:{value[:50]}"  # Limitar tamanho
            except Exception:
                continue
                
    except Exception:
        pass

    # Estratégia 3: Timestamp + posição
    try:
        # Buscar timestamp no post
        timestamp = ""
        time_selectors = [
            "time[datetime]",
            "span[class*='timestamp']",
            "a[href*='story_fbid'] span",
            "[data-tooltip-content*='ago'], [data-tooltip-content*='há']"
        ]
        
        for selector in time_selectors:
            try:
                time_elem = post_element.locator(selector).first()
                if await time_elem.count() > 0:
                    # Tentar pegar datetime primeiro
                    datetime_attr = await time_elem.get_attribute("datetime")
                    if datetime_attr:
                        timestamp = datetime_attr
                        break
                    
                    # Senão, pegar texto
                    text = await time_elem.text_content()
                    if text and len(text.strip()) > 0:
                        timestamp = text.strip()
                        break
                        
            except Exception:
                continue
        
        # Obter posição do elemento
        bbox = await post_element.bounding_box()
        position = f"{bbox['x']}_{bbox['y']}" if bbox else "0_0"
        
        # Obter snippet do texto para diferenciação
        text_content = await post_element.text_content() or ""
        text_snippet = text_content[:100].replace('\n', ' ').strip()
        
        # Criar hash único baseado em múltiplos fatores
        unique_string = f"{timestamp}_{position}_{text_snippet}"
        post_hash = hashlib.md5(unique_string.encode("utf-8", errors="ignore")).hexdigest()[:12]
        
        return f"hash:{post_hash}"

    except Exception:
        pass

    # Estratégia 4: Fallback usando texto + índice
    try:
        text_content = await post_element.text_content() or ""
        if text_content.strip():
            # Usar primeiras palavras + timestamp atual como fallback
            words = text_content.split()[:5]
            text_key = "_".join(words).replace('\n', '')[:50]
            fallback_hash = hashlib.md5(f"{text_key}_{datetime.now().isoformat()}".encode()).hexdigest()[:8]
            return f"fallback:{fallback_hash}"
    except Exception:
        pass

    # Se tudo falhar, gerar ID único baseado em timestamp
    fallback_id = f"unknown_{int(datetime.now().timestamp())}"
    return fallback_id

async def extract_post_details(post: Locator):
    """Extrai detalhes do post com validação limpa."""
    bot_logger.debug("Extraindo detalhes do post")

    # Aguardar post estar pronto com novas validações
    await wait_post_ready(post)

    # Expandir texto do artigo antes da extração
    await expand_article_text(post)

    # Extrair autor
    author = await _extract_author(post)
    if not author.strip():
        bot_logger.warning("Autor não encontrado - criando debug dump")
        await debug_dump_article(post, "missing_author")

    # Extrair texto
    text = await _extract_text(post)
    if not text.strip():
        bot_logger.warning("Texto não encontrado - criando debug dump")
        await debug_dump_article(post, "missing_text")

    # Extrair imagens
    images = await _extract_images(post)
    
    # Verificar se há vídeo no post
    video_elem = post.locator("video")
    has_video = await video_elem.count() > 0
    if has_video:
        bot_logger.debug("Post contém vídeo; marcando como conteúdo visual")
    
    if not images and not has_video:
        bot_logger.warning("Imagens não encontradas - criando debug dump")
        await debug_dump_article(post, "missing_images")
    
    # Manter compatibilidade: primeira imagem como principal
    image_url = images[0] if images else ("[vídeo]" if has_video else "")
    images_extra = images[1:] if len(images) > 1 else []

    # Log adicional para debug se post parece vazio
    if not text.strip() and not image_url.strip():
        try:
            # Salvar HTML do post problemático
            html_content = await post.inner_html()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_file = Path(f"debug_dumps/empty_post_{timestamp}.html")
            debug_file.parent.mkdir(exist_ok=True)
            
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            bot_logger.warning(f"Post vazio detectado - HTML salvo em {debug_file}")
        except Exception as e:
            bot_logger.debug(f"Erro ao salvar debug do post vazio: {e}")

    bot_logger.debug(f"Extração: autor='{author}', texto={len(text)} chars, imagens={len(images)}, vídeo={has_video}")

    return {
        "author": author.strip() if author else "",
        "text": text.strip() if text else "",
        "image_url": image_url.strip() if image_url else "",
        "images_extra": images_extra,
        "has_video": has_video
    }

async def _extract_author(post: Locator):
    """
    Extrai autor do post com validação robusta e múltiplas estratégias.
    Procura por links de perfil e filtra elementos de UI.
    """
    
    # Padrões para excluir do autor (expandidos)
    exclude_patterns = [
        r'^\d+\s*(h|hr|hrs|min|mins|m|d|dia|dias|hora|horas|s|sec|seconds)$',
        r'^\d+\s*(h|hr|hrs|min|mins|m|d|dia|dias|hora|horas|s|sec|seconds)\s*(ago|atrás)?$',
        r'^(há|ago)\s+\d+',
        r'^(Like|Comment|Share|Curtir|Comentar|Compartilhar|Reply|Responder)$',
        r'^(Follow|Seguir|See More|Ver Mais|Most Relevant|Top Contributor)$',
        r'^(Show|Mostrar|Hide|Ocultar|Edit|Editar|Delete|Deletar)$',
        r'^·+$',
        r'^\d+$',
        r'^\s*$',
        r'^(Sponsored|Patrocinado|Ad|Anúncio)$',
        r'^(More|Mais|Less|Menos)$'
    ]
    
    # Estratégia 1: Links de perfil com span[dir="auto"] não ocultos
    try:
        # Seletores mais robustos para perfis
        profile_selectors = [
            # Links diretos de perfil com spans visíveis
            'a[role="link"][href*="/user/"]:visible span[dir="auto"]:not([aria-hidden="true"])',
            'a[role="link"][href*="/profile.php"]:visible span[dir="auto"]:not([aria-hidden="true"])', 
            'a[role="link"][href*="/people/"]:visible span[dir="auto"]:not([aria-hidden="true"])',
            # Links de perfil em grupos
            'a[role="link"][href*="/groups/"][href*="/user/"]:visible span[dir="auto"]:not([aria-hidden="true"])',
            # Headers com strong/h3
            'h3 a[role="link"] span[dir="auto"]:not([aria-hidden="true"])',
            'strong a[role="link"] span[dir="auto"]:not([aria-hidden="true"])'
        ]
        
        for selector in profile_selectors:
            try:
                elements = post.locator(selector)
                count = await elements.count()
                
                for i in range(count):
                    author_elem = elements.nth(i)
                    if await author_elem.is_visible():
                        text = (await author_elem.text_content() or "").strip()
                        
                        # Validações de nome válido
                        if (text and 
                            len(text) >= 2 and 
                            len(text) <= 100 and
                            not text.isdigit() and
                            '·' not in text and  # Filtrar separadores
                            not any(re.search(pattern, text, re.IGNORECASE) for pattern in exclude_patterns)):
                            
                            # Verificar se parece nome de pessoa (contém letra)
                            if re.search(r'[a-zA-ZÀ-ÿ]', text):
                                return text
                                
            except Exception:
                continue
                
    except Exception:
        pass
    
    # Estratégia 2: Buscar por links de perfil no cabeçalho do post
    try:
        # Primeiro, tentar encontrar o cabeçalho via timestamp
        time_elem = post.locator("time").first()
        if await time_elem.count() > 0:
            # Subir para encontrar container do cabeçalho
            for level in range(1, 4):
                try:
                    header = time_elem.locator(f"xpath=ancestor::div[{level}]")
                    if await header.count() > 0:
                        # Buscar links de perfil no cabeçalho
                        profile_links = header.locator('a[role="link"]')
                        count = await profile_links.count()
                        
                        for i in range(count):
                            link = profile_links.nth(i)
                            href = await link.get_attribute("href") or ""
                            
                            # Verificar se é link de perfil
                            if any(pattern in href for pattern in ["/user/", "/profile.php", "facebook.com"]):
                                text = (await link.text_content() or "").strip()
                                
                                if (text and 
                                    len(text) >= 2 and 
                                    len(text) <= 100 and
                                    not any(term in text.lower() for term in [
                                        "·", "min", "h", "d", "ago", "há", "curtir", "comentar",
                                        "compartilhar", "like", "comment", "share", "follow", "seguir"
                                    ])):
                                    return text
                except Exception:
                    continue
                    
    except Exception:
        pass
    
    # Estratégia 3: Tentar obter o nome diretamente do link do perfil no cabeçalho
    try:
        profile_link = post.locator("h3 a[role='link']:visible").first()
        if await profile_link.count() > 0:
            full_text = (await profile_link.text_content() or "").strip()
            # Se o texto do link tiver um separador "·", pegar apenas a parte antes
            name_only = full_text.split('·')[0].strip()
            if name_only and not any(re.search(pattern, name_only, re.IGNORECASE) for pattern in exclude_patterns):
                return name_only
    except Exception:
        pass
    
    # Estratégia 4: Fallback - buscar qualquer link de perfil válido
    try:
        all_links = post.locator('a[role="link"]:visible')
        count = await all_links.count()
        
        for i in range(count):
            link = all_links.nth(i)
            href = await link.get_attribute("href") or ""
            
            # Verificar se parece link de perfil
            if any(pattern in href for pattern in ["/user/", "/profile.php"]):
                text = (await link.text_content() or "").strip()
                
                # Validar nome usando regex patterns
                if (text and 
                    len(text) >= 2 and 
                    len(text) <= 100 and
                    not text.isdigit() and
                    not any(re.search(pattern, text, re.IGNORECASE) for pattern in exclude_patterns)):
                    return text
                    
    except Exception:
        pass
    
    return ""

async def _extract_text(post: Locator):
    """Extrai texto do post com expansão automática e filtros robustos."""
    
    # Primeiro, tentar expandir texto usando múltiplas estratégias
    try:
        # Estratégia 1: Botões "Ver mais" tradicionais
        see_more_selectors = [
            'div[role="button"]:has-text("Ver mais")',
            'div[role="button"]:has-text("See more")',
            'span[role="button"]:has-text("Ver mais")',  
            'span[role="button"]:has-text("See more")',
            # Seletores mais específicos do Facebook
            '[data-testid="post_message"] div[role="button"]',
            'div[data-ad-preview="message"] div[role="button"]'
        ]
        
        for selector in see_more_selectors:
            try:
                see_more_button = post.locator(selector).first()
                if await see_more_button.count() > 0 and await see_more_button.is_visible():
                    button_text = await see_more_button.text_content()
                    if button_text and ('ver mais' in button_text.lower() or 'see more' in button_text.lower()):
                        bot_logger.debug("Expandindo texto: clicando em 'Ver mais'")
                        await see_more_button.click()
                        await asyncio.sleep(1.5)  # Aguardar expansão
                        break
            except Exception:
                continue
                
        # Estratégia 2: Usar get_by_role para "Ver mais"
        try:
            see_more_by_role = post.get_by_role("button", name=re.compile(r"See more|Ver mais", re.IGNORECASE))
            if await see_more_by_role.count() > 0:
                bot_logger.debug("Expandindo texto: get_by_role")
                await see_more_by_role.first().click()
                await asyncio.sleep(1.5)
        except Exception:
            pass
            
    except Exception:
        bot_logger.debug("Erro ao tentar expandir texto")
    
    # Estratégia 1: Buscar div[dir="auto"] visíveis e não ocultos
    try:
        elements = post.locator('div[dir="auto"]:visible:not([aria-hidden="true"])')
        all_texts = []
        
        count = await elements.count()
        for i in range(count):
            elem = elements.nth(i)
            # Verificar se elemento está realmente visível
            if await elem.is_visible():
                text = (await elem.text_content() or "").strip()
                if text:
                    all_texts.append(text)
        
        # Filtrar textos válidos
        ui_terms = [
            'responder', 'comentar', 'compartilhar', 'curtir',
            'reply', 'comment', 'share', 'like',
            'ver mais', 'see more', 'mostrar mais', 'ver más', 'voir plus',
            'follow', 'seguir', 'unfollow'
        ]
        
        filtered_texts = []
        for text in all_texts:
            text_clean = text.strip()
            text_lower = text_clean.lower()
            
            # Filtrar textos curtos demais ou de UI
            if (len(text_clean) > 1 and 
                not re.match(r'^(responder|comentar|ver mais|see more)$', text_lower) and
                not any(ui_term in text_lower for ui_term in ui_terms) and
                not re.match(r'^\d+\s*(h|hr|hrs|min|mins|m|d|dia|dias|hora|horas|s|sec|seconds)', text_lower)):
                filtered_texts.append(text_clean)
        
        if filtered_texts:
            # Juntar textos válidos
            combined_text = '\n'.join(filtered_texts)
            
            # Remover padrões de "Ver mais" e similares
            see_more_patterns = [
                r'\b(See more|Ver mais|Mostrar mais|Ver más|Voir plus)\b',
                r'\b(Continuar lendo|Continue reading|Lire la suite)\b'
            ]
            
            for pattern in see_more_patterns:
                combined_text = re.sub(pattern, '', combined_text, flags=re.IGNORECASE)
            
            # Normalizar espaços e quebras
            combined_text = re.sub(r'\n+', '\n', combined_text)
            combined_text = re.sub(r' +', ' ', combined_text)
            combined_text = combined_text.strip()
            
            if len(combined_text) >= 10:
                return combined_text
                
    except Exception as e:
        bot_logger.debug(f"Erro na extração de texto estratégia 1: {e}")
    
    # Estratégia 2: Fallback usando MESSAGE_CANDIDATES
    try:
        from .selectors import MESSAGE_CANDIDATES
        
        for selector in MESSAGE_CANDIDATES:
            try:
                elements = post.locator(selector)
                count = await elements.count()
                
                if count > 0:
                    text_parts = []
                    for i in range(count):
                        elem = elements.nth(i)
                        text = (await elem.text_content() or "").strip()
                        if text and len(text) >= 10:
                            text_parts.append(text)
                    
                    if text_parts:
                        combined_text = " ".join(text_parts)
                        combined_text = re.sub(r'\s+', ' ', combined_text).strip()
                        
                        if len(combined_text) >= 10:
                            return combined_text
                            
            except Exception:
                continue
                
    except Exception as e:
        bot_logger.debug(f"Erro na extração de texto estratégia 2: {e}")
    
    return ""

async def _extract_images(post: Locator):
    """Extrai URLs de todas as imagens do post incluindo img, background-image e svg."""
    
    try:
        # Usar evaluate para capturar todos os tipos de imagem
        image_urls = await post.evaluate("""
            (el) => {
                const urls = new Set();

                // 1. Imagens <img> tradicionais
                el.querySelectorAll('img').forEach(img => {
                    const u = img.currentSrc || img.src;
                    if (u && u.includes('scontent')) {
                        urls.add(u);
                    }
                });

                // 2. Background-image em CSS
                el.querySelectorAll('[style*="background-image"]').forEach(elem => {
                    const style = elem.style.backgroundImage;
                    const match = style.match(/url\\(["']?([^"')]+)["']?\\)/i);
                    if (match && match[1] && match[1].includes('scontent')) {
                        urls.add(match[1]);
                    }
                });

                // 3. SVG images (xlink:href e href)
                el.querySelectorAll('svg image').forEach(svgImg => {
                    const href = svgImg.getAttribute('xlink:href') || svgImg.getAttribute('href');
                    if (href && href.includes('scontent')) {
                        urls.add(href);
                    }
                });

                return Array.from(urls);
            }
        """)
        
        # Filtrar e validar URLs
        valid_images = []
        for url in image_urls:
            try:
                # Verificar se é uma URL válida e tem conteúdo do Facebook
                if (url and 
                    isinstance(url, str) and 
                    url.strip() and 
                    'scontent' in url and
                    not url.startswith('data:')):
                    valid_images.append(url.strip())
            except Exception:
                continue
        
        # Remover duplicatas mantendo ordem
        seen = set()
        unique_images = []
        for img_url in valid_images:
            if img_url not in seen:
                seen.add(img_url)
                unique_images.append(img_url)
        
        bot_logger.debug(f"Imagens extraídas: {len(unique_images)}")
        return unique_images
        
    except Exception as e:
        bot_logger.debug(f"Erro na extração de imagens: {e}")
        return []