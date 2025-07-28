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
    """Navega para um grupo do Facebook."""
    bot_logger.info(f"Acessando grupo: {group_url}")
    await page.goto(group_url, wait_until='domcontentloaded')

    try:
        await page.wait_for_selector(FEED, timeout=25000)
        await asyncio.sleep(2)
        bot_logger.success("Feed do grupo carregado")
    except Exception as e:
        bot_logger.warning(f"Erro ao carregar feed: {e}")

async def iterate_posts(page: Page, max_posts: int = 15, scroll_delay: float = 1.0):
    """
    Itera pelos posts do feed com rolagem progressiva.
    
    Args:
        page: Página do Playwright
        max_posts: Número máximo de posts a processar
        scroll_delay: Delay entre scrolls (configurável)
        
    Yields:
        Locator: Elementos de posts válidos
    """
    bot_logger.debug(f"Iniciando iteração de posts (máx: {max_posts})")
    
    # Garantir que o feed esteja visível
    try:
        await page.wait_for_selector(FEED, timeout=10000)
    except Exception:
        bot_logger.warning("Timeout aguardando feed")
        return
    
    processed_count = 0
    last_article_count = 0
    scroll_attempts = 0
    max_scroll_attempts = 10
    
    while processed_count < max_posts and scroll_attempts < max_scroll_attempts:
        try:
            # Buscar todos os artigos no feed
            feed_locator = page.locator(FEED)
            articles = feed_locator.locator(ARTICLE)
            current_article_count = await articles.count()
            
            bot_logger.debug(f"Artigos encontrados: {current_article_count}, processados: {processed_count}")
            
            # Processar novos artigos encontrados
            for i in range(processed_count, min(current_article_count, max_posts)):
                try:
                    article = articles.nth(i)
                    
                    # Verificar se o elemento é válido
                    if not await article.is_visible():
                        continue
                    
                    # Rolar até o artigo
                    await article.scroll_into_view_if_needed()
                    await asyncio.sleep(scroll_delay)
                    
                    # Verificar conteúdo básico
                    text_content = await article.text_content()
                    if not text_content or len(text_content.strip()) < 20:
                        continue
                    
                    # Filtrar elementos de interface
                    ui_indicators = [
                        'like', 'comment', 'share', 'curtir', 'comentar', 'compartilhar',
                        'most relevant', 'top contributor', 'follow', 'seguir'
                    ]
                    
                    text_lower = text_content.lower()
                    if len(text_content) < 50 and any(ui in text_lower for ui in ui_indicators):
                        continue
                    
                    bot_logger.debug(f"Processando post {i + 1}: {text_content[:50]}...")
                    processed_count += 1
                    yield article
                    
                except Exception as e:
                    bot_logger.debug(f"Erro processando artigo {i}: {e}")
                    continue
            
            # Se não há novos artigos, tentar rolar para carregar mais
            if current_article_count == last_article_count:
                bot_logger.debug("Nenhum novo artigo encontrado, rolando para baixo...")
                await page.mouse.wheel(0, 1200)
                await asyncio.sleep(scroll_delay * 2)  # Aguardar carregamento
                scroll_attempts += 1
            else:
                scroll_attempts = 0  # Reset contador se novos artigos foram encontrados
                
            last_article_count = current_article_count
            
        except Exception as e:
            bot_logger.warning(f"Erro na iteração de posts: {e}")
            break
    
    bot_logger.debug(f"Iteração concluída: {processed_count} posts processados")

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
    """Extrai ID único do post."""
    # Estratégia 1: Links diretos
    try:
        link_selectors = [
            "a[href*='/posts/']",
            "a[href*='/permalink/']", 
            "a[href*='/story.php']",
            "a[href*='story_fbid']"
        ]

        for selector in link_selectors:
            try:
                link = post_element.locator(selector).first
                if await link.count() > 0:
                    href = await link.get_attribute("href")
                    if href:
                        clean_href = href.split("?")[0].split("#")[0]
                        if any(pattern in clean_href for pattern in ['/posts/', '/permalink/', 'story_fbid']):
                            return clean_href
            except Exception:
                continue
    except Exception:
        pass

    # Estratégia 2: Atributos data
    try:
        data_attrs = ['data-ft', 'data-testid', 'id', 'data-story-id']
        for attr in data_attrs:
            value = await post_element.get_attribute(attr)
            if value:
                return f"attr:{attr}:{value}"
    except Exception:
        pass

    # Estratégia 3: Hash do conteúdo
    try:
        text_content = await post_element.text_content()
        bbox = await post_element.bounding_box()

        # Buscar timestamp
        timestamp = ""
        try:
            time_elem = post_element.locator("time, span[class*='timestamp']").first
            if await time_elem.count() > 0:
                timestamp = await time_elem.get_attribute("datetime") or await time_elem.text_content() or ""
        except Exception:
            pass

        # Criar hash único
        unique_string = f"{text_content[:200]}_{bbox['x'] if bbox else 0}_{bbox['y'] if bbox else 0}_{timestamp}"
        post_hash = hashlib.md5(unique_string.encode("utf-8", errors="ignore")).hexdigest()
        return f"hash:{post_hash}"

    except Exception:
        pass

    return None

async def extract_post_details(post: Locator):
    """Extrai detalhes do post com validação limpa."""
    bot_logger.debug("Extraindo detalhes do post")

    await asyncio.sleep(2)  # Aguardar renderização

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
    if not images:
        bot_logger.warning("Imagens não encontradas - criando debug dump")
        await debug_dump_article(post, "missing_images")
    
    # Manter compatibilidade: primeira imagem como principal
    image_url = images[0] if images else ""
    images_extra = images[1:] if len(images) > 1 else []

    bot_logger.debug(f"Extração: autor='{author}', texto={len(text)} chars, imagens={len(images)}")

    return {
        "author": author.strip() if author else "",
        "text": text.strip() if text else "",
        "image_url": image_url.strip() if image_url else "",
        "images_extra": images_extra
    }

async def _extract_author(post: Locator):
    """Extrai autor do post de forma robusta usando timestamp como âncora."""
    
    # Estratégia 1: Localizar timestamp e subir ao container do cabeçalho
    try:
        time_elem = post.locator("time").first
        if await time_elem.count() > 0:
            # Tentar diferentes níveis de ancestrais para encontrar o container do título
            for ancestor_level in range(1, 4):
                try:
                    header_container = time_elem.locator(f"xpath=ancestor::div[{ancestor_level}]")
                    if await header_container.count() > 0:
                        # Procurar link de perfil dentro do container
                        profile_links = header_container.locator("a[role='link']")
                        count = await profile_links.count()
                        
                        for i in range(count):
                            link = profile_links.nth(i)
                            href = await link.get_attribute("href") or ""
                            text = (await link.text_content() or "").strip()
                            
                            # Validar se é um link de perfil válido
                            if ("facebook.com" in href and 
                                text and 
                                len(text) >= 2 and 
                                len(text) <= 100 and
                                not any(term in text.lower() for term in ["·", "min", "h", "d", "ago", "curtir", "comentar", "compartilhar", "like", "comment", "share"])):
                                return text
                                
                except Exception:
                    continue
                    
    except Exception:
        pass
    
    # Estratégia 2: Fallback - buscar primeiro link válido no post
    try:
        all_links = post.get_by_role("link")
        count = await all_links.count()
        
        for i in range(count):
            link = all_links.nth(i)
            text = (await link.text_content() or "").strip()
            href = await link.get_attribute("href") or ""
            
            # Validar que parece um nome (≥ 2 palavras, sem números puros)
            if (text and 
                len(text.split()) >= 2 and 
                len(text) >= 2 and 
                len(text) <= 100 and
                not text.isdigit() and
                "facebook.com" in href and
                not any(term in text.lower() for term in ["·", "min", "h", "d", "ago", "curtir", "comentar", "compartilhar", "like", "comment", "share", "follow", "seguir"])):
                return text
                
    except Exception:
        pass
    
    return ""

async def _extract_text(post: Locator):
    """Extrai texto do post usando MESSAGE_CANDIDATES."""
    from .selectors import MESSAGE_CANDIDATES
    
    # Estratégia 1: Iterar sobre MESSAGE_CANDIDATES
    for selector in MESSAGE_CANDIDATES:
        try:
            elements = post.locator(selector)
            count = await elements.count()
            
            if count > 0:
                text_parts = []
                for i in range(count):
                    elem = elements.nth(i)
                    text = (await elem.text_content() or "").strip()
                    if text:
                        text_parts.append(text)
                
                if text_parts:
                    # Juntar e normalizar espaços
                    combined_text = " ".join(text_parts)
                    combined_text = re.sub(r'\s+', ' ', combined_text).strip()
                    
                    if combined_text:
                        # Remover tokens "See more", "Ver mais", etc.
                        see_more_patterns = [
                            r'\b(See more|Ver mais|Mostrar mais|Ver más|Voir plus)\b',
                        ]
                        
                        for pattern in see_more_patterns:
                            combined_text = re.sub(pattern, '', combined_text, flags=re.IGNORECASE)
                        
                        # Normalizar espaços novamente após remoção
                        combined_text = re.sub(r'\s+', ' ', combined_text).strip()
                        
                        if len(combined_text) >= 10:
                            return combined_text
                        
        except Exception:
            continue
    
    # Estratégia 2: Fallback usando div[dir='auto']
    try:
        elements = post.locator("div[dir='auto']")
        all_texts = await elements.all_inner_texts()
        
        # Filtrar itens curtos ou de UI
        ui_terms = [
            'curtir', 'comentar', 'compartilhar', 'like', 'comment', 'share',
            'see more', 'ver mais', 'mostrar mais', 'ver más', 'voir plus',
            'follow', 'seguir', 'reply', 'responder'
        ]
        
        filtered_texts = []
        for text in all_texts:
            text = text.strip()
            if (len(text) >= 10 and 
                not any(term in text.lower() for term in ui_terms) and
                not re.match(r'^\d+\s*(h|hr|hrs|min|mins|m|d|dia|dias|hora|horas|s|sec|seconds)', text.lower())):
                filtered_texts.append(text)
        
        if filtered_texts:
            # Juntar e normalizar
            combined_text = " ".join(filtered_texts)
            combined_text = re.sub(r'\s+', ' ', combined_text).strip()
            
            # Remover tokens "See more", "Ver mais", etc.
            see_more_patterns = [
                r'\b(See more|Ver mais|Mostrar mais|Ver más|Voir plus)\b',
            ]
            
            for pattern in see_more_patterns:
                combined_text = re.sub(pattern, '', combined_text, flags=re.IGNORECASE)
            
            # Normalizar espaços novamente
            combined_text = re.sub(r'\s+', ' ', combined_text).strip()
            
            if len(combined_text) >= 10:
                return combined_text
                
    except Exception:
        pass
    
    return ""

async def _extract_images(post: Locator):
    """Extrai URLs de todas as imagens do post."""
    from .selectors import IMG_CANDIDATE
    
    images = []
    
    try:
        img_elements = post.locator(IMG_CANDIDATE)
        count = await img_elements.count()
        
        for i in range(count):
            img_elem = img_elements.nth(i)
            
            try:
                # Verificar se tem srcset (maior qualidade)
                srcset = await img_elem.get_attribute("srcset")
                src = None
                
                if srcset:
                    # Pegar a última URL do srcset (maior resolução)
                    urls = [url.strip().split(' ')[0] for url in srcset.split(',')]
                    src = urls[-1] if urls else None
                
                # Se não tem srcset, usar src
                if not src:
                    src = await img_elem.get_attribute("src")
                
                # Validar URL
                if not src or not src.strip() or "scontent" not in src:
                    continue
                
                # Verificar dimensões reais usando evaluate
                dimensions = await img_elem.evaluate("""
                    (img) => ({
                        naturalWidth: img.naturalWidth,
                        naturalHeight: img.naturalHeight
                    })
                """)
                
                # Filtrar por tamanho mínimo
                if (dimensions.get('naturalWidth', 0) >= 120 and 
                    dimensions.get('naturalHeight', 0) >= 120):
                    images.append(src.strip())
                    
            except Exception:
                continue
                
    except Exception:
        pass
    
    return images