import asyncio
import hashlib
import logging
import re
from playwright.async_api import Page, Locator
from logger import bot_logger

async def navigate_to_group(page: Page, group_url: str):
    """Navega para um grupo do Facebook."""
    bot_logger.info(f"Acessando grupo: {group_url}")
    await page.goto(group_url, wait_until='domcontentloaded')

    try:
        await page.wait_for_selector("div[role='feed']", timeout=25000)
        await asyncio.sleep(2)
        bot_logger.success("Feed do grupo carregado")
    except Exception as e:
        bot_logger.warning(f"Erro ao carregar feed: {e}")

async def find_next_valid_post(page: Page, skip_count: int = 0):
    """Encontra o próximo post válido."""
    bot_logger.debug(f"Buscando post #{skip_count + 1}")

    # Ir para o topo
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(2)

    # Aguardar feed
    try:
        await page.wait_for_selector("div[role='feed']", timeout=10000)
    except Exception:
        bot_logger.warning("Timeout aguardando feed")

    # Seletores de posts
    post_selectors = [
        "div[role='feed'] div[role='article']",
        "div[role='feed'] div[class*='x1yztbdb']",
        "div[class*='userContentWrapper']",
        "div[data-testid*='story-subtitle'] >> xpath=ancestor::div[contains(@class, 'story_body_container')]",
        "div[class*='story_body_container']"
    ]

    valid_posts = []

    for selector in post_selectors:
        try:
            elements = await page.locator(selector).all()
            if not elements:
                continue

            # Filtrar elementos válidos
            for elem in elements:
                try:
                    if not await elem.is_visible():
                        continue

                    bbox = await elem.bounding_box()
                    if not bbox or bbox['y'] < 0:
                        continue

                    # Verificar conteúdo
                    text_content = await elem.text_content()
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

                    valid_posts.append({
                        'element': elem,
                        'y_position': bbox['y'],
                        'text_preview': text_content[:50]
                    })

                except Exception:
                    continue

            if valid_posts:
                break

        except Exception:
            continue

    if not valid_posts:
        return None

    # Ordenar por posição Y
    valid_posts.sort(key=lambda x: x['y_position'])

    # Retornar post na posição skip_count
    if len(valid_posts) > skip_count:
        selected_post = valid_posts[skip_count]
        bot_logger.debug(f"Post selecionado: {selected_post['text_preview']}")

        # Centralizar o post
        await selected_post['element'].scroll_into_view_if_needed()
        await asyncio.sleep(2)

        return selected_post['element']

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

    # Extrair autor
    author = await _extract_author(post)

    # Extrair texto
    text = await _extract_text(post)

    # Extrair imagem
    image_url = await _extract_image(post)

    bot_logger.debug(f"Extração: autor='{author}', texto={len(text)} chars, imagem={'sim' if image_url else 'não'}")

    return {
        "author": author.strip() if author else "",
        "text": text.strip() if text else "",
        "image_url": image_url.strip() if image_url else ""
    }

async def _extract_author(post: Locator):
    """Extrai autor do post."""
    author_strategies = [
        [
            "h3 a[href*='facebook.com/'] strong",
            "h3 a[href*='/user/'] strong", 
            "h3 a[href*='/profile/'] strong",
            "h3 a[role='link'] strong:not(:has-text('·')):not(:has-text('min')):not(:has-text('h')):not(:has-text('d'))",
        ],
        [
            "h3 span[dir='auto']:not(:has-text('·')):not(:has-text('min')):not(:has-text('h')):not(:has-text('d')):not(:has-text('ago'))",
            "h3 span[class*='x1lliihq']:not(:has-text('·')):not(:has-text('min')):not(:has-text('h')):not(:has-text('d'))",
        ],
        [
            "h3 strong:not(:near(time)):not(:has-text('min')):not(:has-text('h')):not(:has-text('d')):not(:has-text('ago'))",
            "h3 span strong:not(:has-text('·')):not(:has-text('min'))",
        ]
    ]

    # Padrões para excluir
    exclude_patterns = [
        r'^\d+\s*(h|hr|hrs|min|mins|m|d|dia|dias|hora|horas|s|sec|seconds)$',
        r'^\d+\s*(h|hr|hrs|min|mins|m|d|dia|dias|hora|horas|s|sec|seconds)\s*(ago|atrás)?$',
        r'^(há|ago)\s+\d+',
        r'^(Like|Comment|Share|Curtir|Comentar|Compartilhar|Reply|Responder)$',
        r'^(Follow|Seguir|See More|Ver Mais|Most Relevant|Top Contributor)$',
        r'^·$',
        r'^\d+$',
        r'^\s*$',
    ]

    for selectors in author_strategies:
        for selector in selectors:
            try:
                author_elems = post.locator(selector)
                count = await author_elems.count()

                for j in range(count):
                    elem = author_elems.nth(j)
                    potential_author = (await elem.text_content() or "").strip()

                    if not potential_author or len(potential_author) < 2 or len(potential_author) > 100:
                        continue

                    # Verificar padrões excluídos
                    is_excluded = any(re.search(pattern, potential_author, re.IGNORECASE) for pattern in exclude_patterns)

                    if not is_excluded:
                        return potential_author

            except Exception:
                continue

    return ""

async def _extract_text(post: Locator):
    """Extrai texto do post."""
    text_strategies = [
        [
            "div[data-ad-preview='message']",
            "div[data-testid*='post_message']", 
            "div[class*='userContent']",
            "div[class*='text_exposed_root']",
        ],
        [
            "div[dir='auto']:not(:near(h3)):not(:near(time)) span[dir='auto']",
            "span[dir='auto']:not(:near(h3)):not(:near(time)):not(:has-text('Like')):not(:has-text('Comment'))",
            "div[class*='x1iorvi4']:not(:near(h3)) span[dir='auto']",
        ],
        [
            "div:not(:near(h3)):not([class*='comment']):not([class*='reaction']):not([class*='timestamp']) p",
            "div:not(:near(h3)):not([class*='comment']):not([class*='reaction']) span:not(:has-text('Like')):not(:has-text('Share'))",
        ]
    ]

    # Padrões para excluir
    exclude_patterns = [
        r'^(Like|Comment|Share|Curtir|Comentar|Compartilhar|Responder|Reply)$',
        r'^(Follow|Seguir|See More|Ver Mais|Most Relevant|Top Contributor)$',
        r'^\d+\s*(like|curtir|comment|comentário|share|compartilhar)s?$',
        r'^\d+\s*(h|hr|hrs|min|mins|m|d|dia|dias|hora|horas)\s*(ago|atrás)?$',
        r'^(há|ago)\s+\d+',
        r'^·$',
        r'^\d+$',
        r'^(Translate|Traduzir|See Translation|Ver Tradução)$',
    ]

    collected_text_parts = []

    for selectors in text_strategies:
        for selector in selectors:
            try:
                text_elements = post.locator(selector)
                count = await text_elements.count()

                for j in range(count):
                    elem = text_elements.nth(j)
                    elem_text = (await elem.text_content() or "").strip()

                    if not elem_text or len(elem_text) < 5:
                        continue

                    # Verificar padrões excluídos
                    is_excluded = any(re.search(pattern, elem_text, re.IGNORECASE) for pattern in exclude_patterns)

                    if not is_excluded and elem_text not in collected_text_parts:
                        collected_text_parts.append(elem_text)

                if collected_text_parts:
                    return "\n".join(collected_text_parts)

            except Exception:
                continue

    return ""

async def _extract_image(post: Locator):
    """Extrai URL da imagem do post."""
    image_strategies = [
        [
            "img[src*='scontent']:not([src*='profile']):not([src*='avatar'])",
            "img[src*='fbcdn']:not([src*='static']):not([src*='profile'])",
        ],
        [
            "img[class*='scaledImageFitWidth']",
            "img[class*='x1ey2m1c']:not([class*='profile']):not([src*='emoji'])",
            "img[referrerpolicy='origin-when-cross-origin']:not([src*='emoji']):not([src*='static'])",
        ],
        [
            "div[class*='uiScaledImageContainer'] img:not([src*='profile'])",
            "div[class*='_46-f'] img:not([src*='profile']):not([src*='avatar'])",
        ]
    ]

    for selectors in image_strategies:
        for selector in selectors:
            try:
                img_elements = post.locator(selector)
                count = await img_elements.count()

                for j in range(count):
                    img_elem = img_elements.nth(j)
                    src = await img_elem.get_attribute("src")

                    if not src:
                        continue

                    # Validações
                    valid_indicators = ['scontent', 'fbcdn.net']
                    invalid_indicators = [
                        'emoji', 'static', 'profile', 'avatar', 'rsrc.php', 
                        'safe_image', 'icon', 'badge', 'reaction', 'placeholder'
                    ]

                    has_valid = any(indicator in src for indicator in valid_indicators)
                    has_invalid = any(indicator in src for indicator in invalid_indicators)

                    if has_valid and not has_invalid:
                        # Verificar dimensões mínimas
                        try:
                            bbox = await img_elem.bounding_box()
                            if bbox and (bbox['width'] < 80 or bbox['height'] < 80):
                                continue
                        except Exception:
                            pass

                        return src

            except Exception:
                continue

    return ""