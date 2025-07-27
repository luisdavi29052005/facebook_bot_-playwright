import asyncio
import hashlib
import logging
import re
from playwright.async_api import Page, Locator

async def navigate_to_group(page: Page, group_url: str):
    """Navega para um grupo do Facebook"""
    print(f"🌍 Acessando grupo: {group_url}")
    await page.goto(group_url, wait_until='domcontentloaded')

    try:
        await page.wait_for_selector("div[role='feed']", timeout=25000)
        await asyncio.sleep(2)
        print("✅ Feed do grupo carregado")
    except Exception as e:
        print(f"⚠️ Erro ao carregar feed: {e}")

async def get_first_post_from_top(page: Page):
    """Busca o primeiro post visível no topo da página"""

    logging.info("🔍 BUSCANDO PRIMEIRO POST NO TOPO DA PÁGINA...")
    logging.info("📍 Iniciando busca sistemática por posts válidos no feed principal")

    # Scroll para o topo
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(3)

    # Aguardar feed carregar
    try:
        await page.wait_for_selector("div[role='feed']", timeout=10000)
        logging.info("✅ Feed carregado completamente")
    except Exception:
        logging.warning("⚠️ Timeout aguardando feed, continuando...")

    # Seletores ordenados por prioridade
    post_selectors = [
        "div[role='feed'] div[role='article']:first-child",
        "div[role='feed'] div[class*='x1yztbdb']:first-child",
        "div[role='article']",
        "div[class*='userContentWrapper']",
        "div[data-testid*='story-subtitle'] >> xpath=ancestor::div[contains(@class, 'story_body_container')]",
        "div[class*='story_body_container']",
        "div[class*='_427x']"
    ]

    for i, selector in enumerate(post_selectors, 1):
        try:
            logging.info(f"🔍 ESTRATÉGIA {i}/7: Testando seletor CSS: {selector}")
            logging.info(f"⏳ Aguardando localização de elementos...")

            # Buscar elementos com o seletor
            elements = await page.locator(selector).all()

            if elements:
                logging.info(f"✅ SUCESSO: {len(elements)} elementos encontrados com estratégia {i}")
                logging.info(f"📋 Iniciando validação de {min(5, len(elements))} elementos...")

                # Filtrar elementos válidos
                for j, elem in enumerate(elements[:5], 1):
                    try:
                        logging.info(f"🔍 Validando elemento {j}/{min(5, len(elements))}...")
                        
                        if await elem.is_visible():
                            logging.info(f"👁️ Elemento {j} está visível na tela")
                            bbox = await elem.bounding_box()
                            if bbox and bbox['y'] >= 0:
                                logging.info(f"📐 Elemento {j} - Posição: x={bbox['x']}, y={bbox['y']}, largura={bbox['width']}, altura={bbox['height']}")
                                text_content = await elem.text_content()
                                if text_content and len(text_content.strip()) > 10:
                                    logging.info(f"✅ POST VÁLIDO ENCONTRADO!")
                                    logging.info(f"📊 Estatísticas: y={bbox['y']}, texto={len(text_content)} caracteres")
                                    logging.info(f"📄 Preview do conteúdo: {text_content[:100]}...")

                                    # Centralizar o post
                                    await elem.scroll_into_view_if_needed()
                                    await asyncio.sleep(2)

                                    logging.info(f"✅ PRIMEIRO POST SELECIONADO com seletor {i}!")
                                    return elem
                    except Exception as e:
                        logging.debug(f"Erro ao verificar elemento: {e}")
                        continue
            else:
                logging.debug(f"Seletor {i} não encontrou elementos")

        except Exception as e:
            logging.debug(f"Seletor {i} falhou: {e}")
            continue

    # Tentativa final: buscar qualquer div com conteúdo significativo
    logging.warning("🔄 TENTATIVA FINAL: Buscando qualquer elemento com conteúdo...")
    try:
        content_divs = await page.locator("div[role='feed'] div").filter(
            has_text=re.compile(r'.{20,}')  # Pelo menos 20 caracteres
        ).all()

        for div in content_divs[:3]:
            try:
                if await div.is_visible():
                    bbox = await div.bounding_box()
                    if bbox and bbox['y'] > 0:
                        text = await div.text_content()
                        logging.info(f"✅ FALLBACK: Post encontrado com texto: {text[:50]}...")
                        await div.scroll_into_view_if_needed()
                        await asyncio.sleep(2)
                        return div
            except Exception:
                continue
    except Exception:
        pass

    logging.warning("❌ NENHUM POST ENCONTRADO no topo da página!")
    return None

async def find_next_valid_post(page: Page, skip_count: int = 0):
    """Encontra o próximo post válido, pulando os primeiros skip_count posts"""

    logging.info(f"🔍 BUSCANDO PRÓXIMO POST VÁLIDO (pulando {skip_count} posts)...")

    # Ir para o topo
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(2)

    # Aguardar feed
    try:
        await page.wait_for_selector("div[role='feed']", timeout=10000)
        logging.info("✅ Feed carregado completamente")
    except Exception:
        logging.warning("⚠️ Timeout aguardando feed, continuando...")

    # Seletores de posts
    post_selectors = [
        "div[role='feed'] div[role='article']",
        "div[role='feed'] div[class*='x1yztbdb']",
        "div[class*='userContentWrapper']",
        "div[data-testid*='story-subtitle'] >> xpath=ancestor::div[contains(@class, 'story_body_container')]",
        "div[class*='story_body_container']"
    ]

    valid_posts = []

    for selector_num, selector in enumerate(post_selectors, 1):
        try:
            logging.info(f"🔍 Testando seletor {selector_num}: {selector}")
            elements = await page.locator(selector).all()

            if not elements:
                logging.debug(f"Seletor {selector_num}: nenhum elemento encontrado")
                continue

            logging.info(f"📊 Seletor {selector_num} encontrou {len(elements)} elementos")

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
                        'text_preview': text_content[:100]
                    })

                except Exception as e:
                    logging.debug(f"Erro ao validar elemento: {e}")
                    continue

            if valid_posts:
                logging.info(f"✅ Encontrados {len(valid_posts)} posts válidos com seletor {selector_num}")
                break

        except Exception as e:
            logging.debug(f"Seletor {selector_num} falhou: {e}")
            continue

    if not valid_posts:
        logging.warning("❌ Nenhum post válido encontrado")
        return None

    # Ordenar por posição Y (topo para baixo)
    valid_posts.sort(key=lambda x: x['y_position'])

    # Retornar o post na posição skip_count
    if len(valid_posts) > skip_count:
        selected_post = valid_posts[skip_count]

        logging.info(f"✅ POST SELECIONADO (#{skip_count + 1}): {selected_post['text_preview']}")
        logging.info(f"📍 Posição Y: {selected_post['y_position']}")

        # Centralizar o post
        await selected_post['element'].scroll_into_view_if_needed()
        await asyncio.sleep(2)

        return selected_post['element']
    else:
        logging.warning(f"❌ Não há posts suficientes. Encontrados: {len(valid_posts)}, Necessário: {skip_count + 1}")
        return None

async def extract_post_id(post_element: Locator):
    """Extrai um ID único do post"""

    # Estratégia 1: Links diretos do post
    try:
        link_selectors = [
            "a[href*='/posts/']",
            "a[href*='/permalink/']", 
            "a[href*='/story.php']",
            "a[href*='story_fbid']",
            "span[class*='timestamp'] >> xpath=ancestor::a",
            "time >> xpath=ancestor::a"
        ]

        for selector in link_selectors:
            try:
                link = post_element.locator(selector).first
                if await link.count() > 0:
                    href = await link.get_attribute("href")
                    if href:
                        clean_href = href.split("?")[0].split("#")[0]
                        if '/posts/' in clean_href or '/permalink/' in clean_href or 'story_fbid' in href:
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

    # Estratégia 4: Fallback with elements children
    try:
        # Search for any link inside the post
        all_links = post_element.locator(".//a[@href]")
        count = await all_links.count()
        for j in range(count):
            link = all_links.nth(j)
            href = await link.get_attribute("href")
            if href and ("facebook.com" in href or "fb.com" in href):
                return f"link:{href.split('?')[0]}"
    except Exception:
        pass

    return None

async def extract_post_details(post: Locator):
    """Extrai detalhes do post (autor, texto, imagem) com validação rigorosa"""

    logging.info("🔍 INICIANDO EXTRAÇÃO DETALHADA DO POST")
    logging.info("=" * 80)

    # Aguardar renderização completa
    await asyncio.sleep(2)

    # ========== EXTRAÇÃO DO AUTOR ==========
    author = ""
    logging.info("👤 INICIANDO EXTRAÇÃO DO AUTOR DO POST...")
    logging.info("🎯 OBJETIVO: Encontrar nome real do perfil ou página que criou o post")
    logging.info("🚫 EVITAR: Timestamps, elementos de UI, botões de interação")

    # Estratégias mais específicas para autor
    author_strategies = [
        # Estratégia 1: Links diretos de perfil com strong/span
        [
            "h3 a[href*='facebook.com/'] strong",
            "h3 a[href*='/user/'] strong", 
            "h3 a[href*='/profile/'] strong",
            "h3 a[role='link'] strong:not(:has-text('·')):not(:has-text('min')):not(:has-text('h')):not(:has-text('d'))",
        ],
        
        # Estratégia 2: Spans com nomes em cabeçalhos
        [
            "h3 span[dir='auto']:not(:has-text('·')):not(:has-text('min')):not(:has-text('h')):not(:has-text('d')):not(:has-text('ago'))",
            "h3 span[class*='x1lliihq']:not(:has-text('·')):not(:has-text('min')):not(:has-text('h')):not(:has-text('d'))",
        ],
        
        # Estratégia 3: Strong elements não próximos de tempo
        [
            "h3 strong:not(:near(time)):not(:has-text('min')):not(:has-text('h')):not(:has-text('d')):not(:has-text('ago'))",
            "h3 span strong:not(:has-text('·')):not(:has-text('min'))",
        ]
    ]

    # Padrões rigorosos para excluir timestamps e elementos de UI
    author_exclude_patterns = [
        r'^\d+\s*(h|hr|hrs|min|mins|m|d|dia|dias|hora|horas|s|sec|seconds)$',
        r'^\d+\s*(h|hr|hrs|min|mins|m|d|dia|dias|hora|horas|s|sec|seconds)\s*(ago|atrás)?$',
        r'^(há|ago)\s+\d+',
        r'^(Like|Comment|Share|Curtir|Comentar|Compartilhar|Reply|Responder)$',
        r'^(Follow|Seguir|See More|Ver Mais|Most Relevant|Top Contributor)$',
        r'^·$',
        r'^\d+$',
        r'^(Author|Admin|Moderator)$',
        r'^\s*$',
    ]

    for strategy_num, selectors in enumerate(author_strategies, 1):
        if author:
            break

        logging.info(f"👤 ESTRATÉGIA DE AUTOR {strategy_num}/3: Testando {len(selectors)} seletores CSS...")
        logging.info(f"📋 Foco: Links de perfil, spans com nomes, elementos strong...")

        for i, selector in enumerate(selectors):
            try:
                logging.info(f"🔍 Seletor {i+1}/{len(selectors)}: {selector}")
                author_elems = post.locator(selector)
                count = await author_elems.count()
                
                if count > 0:
                    logging.info(f"📊 {count} elementos encontrados para análise")

                for j in range(count):
                    elem = author_elems.nth(j)
                    potential_author = (await elem.text_content() or "").strip()
                    
                    if potential_author:
                        logging.info(f"🔍 Candidato a autor #{j+1}: '{potential_author}'")

                    # Validação básica de tamanho
                    if not potential_author or len(potential_author) < 2 or len(potential_author) > 100:
                        continue

                    # Verificar se não é timestamp ou elemento de UI
                    is_excluded = any(re.search(pattern, potential_author, re.IGNORECASE) for pattern in author_exclude_patterns)

                    if not is_excluded:
                        author = potential_author
                        logging.info(f"🎉 AUTOR VALIDADO E CONFIRMADO!")
                        logging.info(f"✅ Estratégia {strategy_num}, Seletor {i+1} foi bem-sucedido")
                        logging.info(f"👤 AUTOR IDENTIFICADO: '{author}'")
                        logging.info(f"📊 Tamanho: {len(author)} caracteres")
                        break
                    else:
                        logging.info(f"❌ Candidato rejeitado: '{potential_author}' (padrão excluído detectado)")

                if author:
                    break

            except Exception as e:
                logging.debug(f"Erro no seletor {i+1} da estratégia {strategy_num}: {e}")
                continue

    # ========== EXTRAÇÃO DO TEXTO ==========
    text = ""
    logging.info("📝 INICIANDO EXTRAÇÃO DO TEXTO PRINCIPAL DO POST...")
    logging.info("🎯 OBJETIVO: Capturar conteúdo real escrito pelo usuário")
    logging.info("🚫 EVITAR: Botões, links de UI, elementos de interface, timestamps")

    # Estratégias para encontrar texto do post
    text_strategies = [
        # Estratégia 1: Containers específicos de conteúdo
        [
            "div[data-ad-preview='message']",
            "div[data-testid*='post_message']", 
            "div[class*='userContent']",
            "div[class*='text_exposed_root']",
        ],
        
        # Estratégia 2: Spans com conteúdo principal
        [
            "div[dir='auto']:not(:near(h3)):not(:near(time)) span[dir='auto']",
            "span[dir='auto']:not(:near(h3)):not(:near(time)):not(:has-text('Like')):not(:has-text('Comment'))",
            "div[class*='x1iorvi4']:not(:near(h3)) span[dir='auto']",
        ],
        
        # Estratégia 3: Parágrafos e divs com texto
        [
            "div:not(:near(h3)):not([class*='comment']):not([class*='reaction']):not([class*='timestamp']) p",
            "div:not(:near(h3)):not([class*='comment']):not([class*='reaction']) span:not(:has-text('Like')):not(:has-text('Share'))",
        ]
    ]

    # Padrões para excluir do texto
    text_exclude_patterns = [
        r'^(Like|Comment|Share|Curtir|Comentar|Compartilhar|Responder|Reply)$',
        r'^(Follow|Seguir|See More|Ver Mais|Most Relevant|Top Contributor)$',
        r'^\d+\s*(like|curtir|comment|comentário|share|compartilhar)s?$',
        r'^\d+\s*(h|hr|hrs|min|mins|m|d|dia|dias|hora|horas)\s*(ago|atrás)?$',
        r'^(há|ago)\s+\d+',
        r'^·$',
        r'^\d+$',
        r'^(Translate|Traduzir|See Translation|Ver Tradução)$',
        r'^(Author|Admin|Moderator)$',
    ]

    collected_text_parts = []

    for strategy_num, selectors in enumerate(text_strategies, 1):
        if collected_text_parts:
            break

        logging.info(f"📝 ESTRATÉGIA DE TEXTO {strategy_num}/3: Analisando {len(selectors)} seletores...")
        logging.info(f"🔍 Foco: Containers de mensagem, spans com conteúdo, parágrafos...")

        for i, selector in enumerate(selectors):
            try:
                logging.info(f"📝 Testando seletor {i+1}/{len(selectors)}: {selector}")
                text_elements = post.locator(selector)
                count = await text_elements.count()
                
                if count > 0:
                    logging.info(f"📊 {count} elementos de texto encontrados")

                for j in range(count):
                    elem = text_elements.nth(j)
                    elem_text = (await elem.text_content() or "").strip()
                    
                    if elem_text:
                        logging.info(f"📄 Fragmento de texto #{j+1} ({len(elem_text)} chars): {elem_text[:50]}...")

                    if not elem_text or len(elem_text) < 5:
                        continue

                    # Verificar padrões excluídos
                    is_excluded = any(re.search(pattern, elem_text, re.IGNORECASE) for pattern in text_exclude_patterns)

                    if not is_excluded and elem_text not in collected_text_parts:
                        collected_text_parts.append(elem_text)

                if collected_text_parts:
                    text = "\n".join(collected_text_parts)
                    logging.info(f"✅ TEXTO ENCONTRADO com estratégia {strategy_num}, seletor {i+1}: {len(text)} chars")
                    logging.info(f"📄 PREVIEW: {text[:100]}...")
                    break

            except Exception as e:
                logging.debug(f"Erro no seletor {i+1} da estratégia {strategy_num}: {e}")
                continue

    # ========== EXTRAÇÃO DE IMAGEM ==========
    image_url = ""
    logging.info("🖼️ INICIANDO BUSCA POR IMAGENS DO POST...")
    logging.info("🎯 OBJETIVO: Encontrar imagens de conteúdo (não avatares ou emojis)")
    logging.info("✅ VÁLIDAS: URLs do scontent.xx.fbcdn.net, fbcdn.net")
    logging.info("❌ INVÁLIDAS: profile, avatar, emoji, static, icons")

    # Estratégias para imagens
    image_strategies = [
        # Estratégia 1: Imagens do Facebook CDN
        [
            "img[src*='scontent']:not([src*='profile']):not([src*='avatar'])",
            "img[src*='fbcdn']:not([src*='static']):not([src*='profile'])",
        ],
        
        # Estratégia 2: Classes específicas de imagem
        [
            "img[class*='scaledImageFitWidth']",
            "img[class*='x1ey2m1c']:not([class*='profile']):not([src*='emoji'])",
            "img[referrerpolicy='origin-when-cross-origin']:not([src*='emoji']):not([src*='static'])",
        ],
        
        # Estratégia 3: Containers de imagem
        [
            "div[class*='uiScaledImageContainer'] img:not([src*='profile'])",
            "div[class*='_46-f'] img:not([src*='profile']):not([src*='avatar'])",
        ]
    ]

    for strategy_num, selectors in enumerate(image_strategies, 1):
        if image_url:
            break

        logging.info(f"🖼️ ESTRATÉGIA DE IMAGEM {strategy_num}/3: Analisando {len(selectors)} seletores...")
        logging.info(f"🔍 Focando em: CDN do Facebook, imagens escaladas, containers específicos")

        for i, selector in enumerate(selectors):
            try:
                logging.info(f"🖼️ Testando seletor {i+1}/{len(selectors)}: {selector}")
                img_elements = post.locator(selector)
                count = await img_elements.count()
                
                if count > 0:
                    logging.info(f"📊 {count} elementos img encontrados")

                for j in range(count):
                    img_elem = img_elements.nth(j)
                    src = await img_elem.get_attribute("src")
                    
                    if src:
                        logging.info(f"🔍 Imagem #{j+1} - URL: {src[:60]}...")
                    if not src:
                        continue

                    # Validações rigorosas para imagem de conteúdo
                    valid_indicators = ['scontent', 'fbcdn.net']
                    invalid_indicators = [
                        'emoji', 'static', 'profile', 'avatar', 'rsrc.php', 
                        'safe_image', 'icon', 'badge', 'reaction', 'placeholder'
                    ]

                    has_valid = any(indicator in src for indicator in valid_indicators)
                    has_invalid = any(indicator in src for indicator in invalid_indicators)

                    if has_valid and not has_invalid:
                        logging.info(f"✅ Imagem passou na validação de URL")
                        
                        # Verificar dimensões mínimas
                        try:
                            bbox = await img_elem.bounding_box()
                            if bbox:
                                logging.info(f"📐 Dimensões: {bbox['width']}x{bbox['height']} pixels")
                                if bbox['width'] < 80 or bbox['height'] < 80:
                                    logging.info(f"❌ Imagem muito pequena (mínimo 80x80)")
                                    continue
                                logging.info(f"✅ Dimensões adequadas para imagem de conteúdo")
                        except Exception as e:
                            logging.info(f"⚠️ Não foi possível verificar dimensões: {e}")

                        image_url = src
                        logging.info(f"🎉 IMAGEM VALIDADA E CONFIRMADA!")
                        logging.info(f"✅ Estratégia {strategy_num}, Seletor {i+1} foi bem-sucedido")
                        logging.info(f"🔗 URL COMPLETA: {image_url}")
                        break
                    else:
                        if not has_valid:
                            logging.info(f"❌ URL não é do CDN do Facebook")
                        if has_invalid:
                            logging.info(f"❌ URL contém indicadores inválidos (profile/emoji/static)")

                if image_url:
                    break

            except Exception as e:
                logging.debug(f"Erro no seletor {i+1} da estratégia {strategy_num}: {e}")
                continue

    # ========== VALIDAÇÃO FINAL E LOGS DETALHADOS ==========
    author = author.strip() if author else ""
    text = text.strip() if text else ""
    image_url = image_url.strip() if image_url else ""

    logging.info("🔍 EXTRAÇÃO FINALIZADA:")
    logging.info(f"   👤 AUTOR: '{author}' ({len(author)} chars)")
    logging.info(f"   📝 TEXTO: {len(text)} chars")
    if text:
        logging.info(f"   📄 TEXTO COMPLETO: {text}")
    logging.info(f"   🖼️ IMAGEM: {'Sim' if image_url else 'Não'}")
    if image_url:
        logging.info(f"   🔗 URL DA IMAGEM: {image_url}")

    return {
        "author": author,
        "text": text,
        "image_url": image_url
    }