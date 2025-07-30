import re
import asyncio
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
from playwright.async_api import Page, Locator

from logger import bot_logger
from .selectors import FacebookSelectors

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
            response = await page.goto(group_url, wait_until='domcontentloaded', timeout=45000)

            if response and response.status >= 400:
                raise Exception(f"Status HTTP {response.status}")

            bot_logger.debug(f"Navegação bem-sucedida (status: {response.status if response else 'N/A'})")

            # Aguardar rede ficar ociosa com timeout maior
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
                bot_logger.debug("NetworkIdle atingido")
            except Exception:
                bot_logger.debug("Timeout networkidle - continuando")

            # Aguardar múltiplos indicadores de carregamento
            feed_indicators = [
                "div[role='feed']",
                "div[role='main']", 
                "div[data-pagelet='GroupFeed']",
                "article[role='article']",
                "div[data-pagelet^='FeedUnit_']"
            ]

            feed_found = False
            for indicator in feed_indicators:
                try:
                    await page.wait_for_selector(indicator, state="attached", timeout=8000)
                    bot_logger.debug(f"Indicador encontrado: {indicator}")
                    feed_found = True
                    break
                except Exception:
                    continue

            if not feed_found:
                bot_logger.warning(f"Nenhum indicador de feed encontrado na tentativa {attempt + 1}")
                # Ainda assim, tentar rolar para ativar carregamento
                await page.mouse.wheel(0, 800)
                await asyncio.sleep(3)

                # Verificar novamente
                for indicator in feed_indicators:
                    try:
                        await page.wait_for_selector(indicator, state="attached", timeout=5000)
                        bot_logger.debug(f"Indicador encontrado após scroll: {indicator}")
                        feed_found = True
                        break
                    except Exception:
                        continue

            if feed_found or attempt == 2:  # Aceitar na última tentativa mesmo sem feed
                # Rolar para ativar o carregamento de posts
                await page.mouse.wheel(0, 1000)
                await asyncio.sleep(2)

                # Aguardar conteúdo adicional carregar
                await asyncio.sleep(3)

                bot_logger.success("Navegação para grupo concluída")
                return
            else:
                raise Exception("Feed não carregou após scroll")

        except Exception as e:
            bot_logger.warning(f"Erro na tentativa {attempt + 1}: {e}")
            if attempt < 2:
                await asyncio.sleep(8)
                continue
            else:
                bot_logger.error(f"Falha após 3 tentativas: {e}")
                # Na última tentativa, aceitar mesmo com erro
                bot_logger.warning("Aceitando navegação com falha - tentando continuar")
                return

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

async def is_valid_post(article) -> bool:
    """
    Valida se o elemento é um post real - OTIMIZADO para processamento sequencial.

    Critérios rápidos para filtrar:
    - Deve ter estrutura de post (role=article OU indicadores básicos)
    - Não deve ser elemento de UI/navegação
    - Deve ter conteúdo mínimo (autor E/OU texto/imagem)

    Args:
        article: Elemento do artigo a ser validado

    Returns:
        bool: True se for um post válido
    """
    try:
        # ═══ VALIDAÇÃO RÁPIDA ═══

        # 1. Verificar role="article" (indicador mais confiável)
        role = await article.get_attribute("role")
        if role == "article":
            # Verificação adicional: não deve ser elemento de UI óbvio
            if not await _is_obvious_ui_element(article):
                bot_logger.debug("✅ Post validado: role=article + não é UI")
                return True

        # 2. Se não tem role="article", fazer verificações mais específicas

        # Verificar se tem indicadores básicos de post
        has_author_indicator = await _has_author_indicator_fast(article)
        has_content_indicator = await _has_content_indicator_fast(article)

        # Precisa ter pelo menos UM indicador válido
        if not (has_author_indicator or has_content_indicator):
            bot_logger.debug("❌ Post rejeitado: sem indicadores básicos")
            return False

        # 3. Filtrar elementos claramente de UI
        if await _is_obvious_ui_element(article):
            bot_logger.debug("❌ Post rejeitado: elemento de UI")
            return False

        # 4. Verificar se tem timestamp (posts reais têm timestamp)
        if await _has_timestamp_indicator(article):
            bot_logger.debug("✅ Post validado: tem timestamp + indicadores")
            return True

        # 5. Fallback: se tem conteúdo suficiente, aceitar
        if has_author_indicator and has_content_indicator:
            bot_logger.debug("✅ Post validado: autor + conteúdo")
            return True

        bot_logger.debug("❌ Post rejeitado: não passou nas validações")
        return False

    except Exception as e:
        bot_logger.debug(f"⚠️ Erro na validação do post: {e}")
        return False

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
        # Pegar apenas primeiros 200 caracteres para performance
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
        has_enough_content = len(relevant_text) >= min_length

        if not has_enough_content:
            bot_logger.debug(f"Conteúdo insuficiente: {len(relevant_text)} chars (mín: {min_length})")

        return has_enough_content

    except Exception as e:
        bot_logger.debug(f"Erro ao verificar conteúdo mínimo: {e}")
        return False

async def find_next_valid_post(page: Page) -> Locator:
    """
    Encontra o PRÓXIMO post válido de forma sequencial - UM POR VEZ.

    Fluxo:
    1. Procura posts visíveis na tela atual
    2. Retorna o PRIMEIRO post válido encontrado
    3. Se não encontrar, rola página e tenta novamente
    4. Foco em processamento individual, não em lote

    Args:
        page: Página do Playwright

    Returns:
        Locator do próximo post válido ou None se não encontrou
    """
    bot_logger.debug("🔍 Buscando próximo post válido (um por vez)...")

    # Verificar se página ainda está ativa
    if page.is_closed():
        bot_logger.warning("Página fechada - cancelando busca")
        return None

    # Aguardar estabilidade da página
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        bot_logger.debug("Timeout domcontentloaded - continuando")

    # Seletores priorizados para posts do Facebook
    post_selectors = FacebookSelectors.get_post_containers()

    # Tentar encontrar post na viewport atual primeiro
    for attempt in range(2):  # Máximo 2 tentativas (atual + scroll)

        if attempt == 1:
            # Segunda tentativa: rolar para carregar mais conteúdo
            bot_logger.debug("📜 Rolando para carregar mais posts...")
            try:
                await page.mouse.wheel(0, 1000)
                await asyncio.sleep(3)  # Aguardar carregamento
            except Exception as e:
                bot_logger.debug(f"Erro ao rolar: {e}")
                break

        # Buscar posts com cada seletor
        for selector_idx, selector in enumerate(post_selectors):
            try:
                bot_logger.debug(f"🔍 Tentativa {attempt + 1} - Seletor {selector_idx + 1}: {selector}")

                posts = page.locator(selector)
                count = await posts.count()

                bot_logger.debug(f"   📊 {count} elementos encontrados")

                if count == 0:
                    continue

                # Verificar posts sequencialmente (máximo 8 para performance)
                max_check = min(count, 8)
                for i in range(max_check):
                    try:
                        post = posts.nth(i)

                        # Verificação básica de visibilidade
                        if not await post.is_visible():
                            continue

                        # Aguardar elemento estar pronto (timeout baixo)
                        try:
                            await post.wait_for_selector('*', timeout=1500)
                        except Exception:
                            pass

                        # Validação de post (filtros de qualidade)
                        if await is_valid_post(post):
                            bot_logger.success(f"✅ POST VÁLIDO encontrado! (seletor: {selector}, posição: {i})")
                            return post

                    except Exception as e:
                        bot_logger.debug(f"   ⚠️ Erro verificando post {i}: {e}")
                        continue

            except Exception as e:
                bot_logger.debug(f"   ❌ Erro com seletor {selector}: {e}")
                continue

    # Se chegou aqui, não encontrou nenhum post válido
    bot_logger.warning("❌ Nenhum post válido encontrado após busca completa")
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

    # Verificação final se é post válido
    if not await is_valid_post(post):
        bot_logger.warning("Post inválido detectado na extração - pulando")
        return {
            "author": "",
            "text": "",
            "image_url": "",
            "images_extra": [],
            "has_video": False
        }

    # Text expansion is now handled within _extract_text function

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
    has_video = await has_video(post)
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

async def _extract_author(post: Locator) -> str:
    """
    Extrai autor do post APENAS a partir do elemento timestamp,
    garantindo que é o autor real do post principal e não de comentários.
    """
    import re

    # Aguardar elementos carregarem
    try:
        await post.wait_for_selector('[href*="comment_id"], time, [aria-label*="há"], [aria-label*="ago"]', timeout=3000)
    except Exception:
        pass

    # ESTRATÉGIA PRINCIPAL: Encontrar o timestamp primeiro e buscar o autor adjacente
    # O timestamp é o indicador mais confiável de onde está o header do post
    timestamp_selectors = [
        'a[href*="comment_id"]',  # Link do timestamp (mais comum)
        'time[datetime]',
        'a[href*="story_fbid"]',
        'span:regex("^\\d+\\s*(min|h|d|dia|dias|hora|horas)$")',
        '[aria-label*="há"]',
        '[aria-label*="ago"]'
    ]

    for ts_selector in timestamp_selectors:
        try:
            timestamp_elements = post.locator(ts_selector)
            ts_count = await timestamp_elements.count()

            for ts_idx in range(min(ts_count, 3)):  # Verificar primeiros 3 timestamps
                try:
                    timestamp_elem = timestamp_elements.nth(ts_idx)

                    if not await timestamp_elem.is_visible():
                        continue

                    # Verificar se é um timestamp válido
                    ts_text = await timestamp_elem.text_content()
                    if not ts_text or not _is_valid_timestamp(ts_text.strip()):
                        continue

                    bot_logger.debug(f"🕒 Timestamp encontrado: '{ts_text.strip()}' - buscando autor adjacente...")

                    # BUSCAR AUTOR NO MESMO CONTAINER/NIVEL DO TIMESTAMP
                    # Estratégias de busca a partir do timestamp
                    author_search_strategies = [
                        # Mesmo container, buscar span/strong anterior
                        'xpath=ancestor::*[1]//a[@role="link"]//span[@dir="auto"]',
                        'xpath=ancestor::*[1]//strong',
                        'xpath=ancestor::*[1]//span[@dir="auto"]',

                        # Container pai, buscar h3 com autor
                        'xpath=ancestor::*[2]//h3//a[@role="link"]//span[@dir="auto"]',
                        'xpath=ancestor::*[2]//h3//strong',

                        # Ir para container do header do post
                        'xpath=ancestor::*[3]//h3//a[@role="link"]//span[@dir="auto"]',
                        'xpath=ancestor::*[3]//h3//strong',

                        # Buscar elementos de autor que precedem o timestamp
                        'xpath=preceding::a[@role="link"]//span[@dir="auto"][1]',
                        'xpath=preceding::strong[1]'
                    ]

                    for search_strategy in author_search_strategies:
                        try:
                            author_candidates = timestamp_elem.locator(search_strategy)
                            auth_count = await author_candidates.count()

                            for auth_idx in range(min(auth_count, 3)):
                                try:
                                    author_elem = author_candidates.nth(auth_idx)

                                    if not await author_elem.is_visible():
                                        continue

                                    author_text = (await author_elem.inner_text() or "").strip()

                                    if not author_text:
                                        continue

                                    # Limpar nome (remover separadores)
                                    clean_name = author_text.split('·')[0].split('•')[0].split('\n')[0].strip()

                                    # Validar se é um nome de pessoa válido
                                    if await _is_valid_author_name(clean_name, author_elem):
                                        # Verificar proximidade ao timestamp (deve estar próximo)
                                        if await _is_author_near_timestamp(author_elem, timestamp_elem):
                                            bot_logger.success(f"✅ AUTOR ENCONTRADO: '{clean_name}' (próximo ao timestamp: '{ts_text.strip()}')")
                                            return clean_name

                                except Exception as e:
                                    bot_logger.debug(f"Erro verificando candidato a autor {auth_idx}: {e}")
                                    continue

                        except Exception as e:
                            bot_logger.debug(f"Erro na estratégia '{search_strategy}': {e}")
                            continue

                except Exception as e:
                    bot_logger.debug(f"Erro processando timestamp {ts_idx}: {e}")
                    continue

        except Exception as e:
            bot_logger.debug(f"Erro na busca de timestamp '{ts_selector}': {e}")
            continue

    # FALLBACK: Buscar autor no primeiro h3 visível do post (sem comentários)
    try:
        bot_logger.debug("🔍 Fallback: buscando primeiro h3 do post...")

        first_h3_strategies = [
            'h3:first-of-type a[role="link"] span[dir="auto"]',
            'h3:first-of-type strong',
            'h3:first-of-type span[dir="auto"]:first-child'
        ]

        for h3_strategy in first_h3_strategies:
            try:
                h3_elements = post.locator(h3_strategy)
                h3_count = await h3_elements.count()

                for i in range(min(h3_count, 2)):
                    try:
                        h3_elem = h3_elements.nth(i)

                        if not await h3_elem.is_visible():
                            continue

                        h3_text = (await h3_elem.inner_text() or "").strip()
                        clean_name = h3_text.split('·')[0].split('•')[0].split('\n')[0].strip()

                        if await _is_valid_author_name(clean_name, h3_elem):
                            # Verificar se não está em área de comentários
                            if not await _is_inside_comment_section(h3_elem):
                                bot_logger.debug(f"✅ Autor encontrado no fallback h3: '{clean_name}'")
                                return clean_name

                    except Exception:
                        continue

            except Exception:
                continue

    except Exception as e:
        bot_logger.debug(f"Erro no fallback h3: {e}")

    bot_logger.warning("❌ AUTOR NÃO ENCONTRADO - nenhuma estratégia funcionou")
    return ""

def _is_valid_timestamp(text: str) -> bool:
    """Valida se o texto parece um timestamp válido."""
    if not text:
        return False

    text_lower = text.lower()

    # Padrões de timestamp válidos
    timestamp_patterns = [
        r'\d+\s*(min|minuto|minutos|m)(?:$|\s)',
        r'\d+\s*(h|hora|horas|hr)(?:$|\s)', 
        r'\d+\s*(d|dia|dias|day|days)(?:$|\s)',
        r'\d+\s*(s|sec|segundo|segundos)(?:$|\s)',
        r'há\s+\d+',
        r'\d+\s*de\s+(janeiro|fevereiro|março|abril|maio|junho)',
        r'\d{1,2}/\d{1,2}',
        r'\d{1,2}:\d{2}'
    ]

    return any(re.search(pattern, text_lower) for pattern in timestamp_patterns)

async def _is_author_near_timestamp(author_elem: Locator, timestamp_elem: Locator) -> bool:
    """Verifica se o elemento do autor está próximo do timestamp (mesmo container)."""
    try:
        # Verificar se estão no mesmo container pai ou próximos
        author_box = await author_elem.bounding_box()
        timestamp_box = await timestamp_elem.bounding_box()

        if not author_box or not timestamp_box:
            return False

        # Calcular distância vertical (devem estar na mesma linha ou próximas)
        vertical_distance = abs(author_box['y'] - timestamp_box['y'])

        # Se estão a menos de 50px de distância vertical, considerar próximos
        return vertical_distance < 50

    except Exception:
        return True  # Se não conseguir calcular, assumir que está próximo

async def _is_valid_author_name(name: str, elem: Locator) -> bool:
    """Valida se o nome extraído é realmente um autor válido."""
    import re

    if not name or len(name) < 2:
        return False

    # Muito longo para ser nome
    if len(name) > 100:
        return False

    # Contém apenas letras, espaços, hífens e acentos
    if not re.match(r'^[A-Za-zÀ-ÿ\s\-\.\']+$', name):
        return False

    # Não pode ser termo de UI (mais rigoroso)
    ui_terms = [
        'like', 'comment', 'share', 'curtir', 'comentar', 'compartilhar',
        'responder', 'reply', 'ver mais', 'see more', 'seguir', 'follow',
        'há', 'ago', 'min', 'hora', 'day', 'yesterday', 'ontem', 'h', 'd',
        'curtida', 'curtidas', 'reagir', 'react', 'reaction', 'reação',
        'photofix', 'studio'  # Filtrar nomes de empresa/página quando aparecem como comentário
    ]

    name_lower = name.lower()

    # Verificar se contém termos de UI
    if any(term in name_lower for term in ui_terms):
        return False

    # Não pode ser timestamp
    if re.match(r'^\d+\s*(min|h|d|hora|horas|dia|dias)', name_lower):
        return False

    # Não pode ser apenas números ou símbolos
    if re.match(r'^[\d\s\-\·\•]+$', name):
        return False

    # Deve ter pelo menos uma letra
    if not re.search(r'[A-Za-zÀ-ÿ]', name):
        return False

    # Verificar se não é termo isolado suspeito
    words = name_lower.split()
    suspicious_single_words = ['sure', 'ok', 'yes', 'no', 'sim', 'não']
    if len(words) == 1 and words[0] in suspicious_single_words:
        return False

    # Deve ter pelo menos 3 caracteres alfabéticos
    alpha_count = sum(1 for c in name if c.isalpha())
    if alpha_count < 3:
        return False

    return True

async def _is_inside_comment_section(elem: Locator) -> bool:
    """Verifica se o elemento está dentro de uma seção de comentários."""
    try:
        # Verificar URL do elemento ou ancestrais (comentários têm comment_id na URL)
        try:
            # Buscar links com comment_id na árvore de ancestrais
            comment_links = elem.locator('xpath=ancestor-or-self::*//a[contains(@href, "comment_id")]')
            if await comment_links.count() > 0:
                bot_logger.debug("❌ Elemento rejeitado: contém link de comentário")
                return True
        except Exception:
            pass

        # Verificar se está dentro de elementos típicos de comentários
        comment_indicators = [
            '[role="article"] [role="article"]',  # Post dentro de post (comentário)
            '[data-testid*="comment"]',
            '[aria-label*="comment"]', 
            '[aria-label*="comentário"]'
        ]

        for indicator in comment_indicators:
            try:
                ancestor_check = elem.locator(f'xpath=ancestor::{indicator}')
                if await ancestor_check.count() > 0:
                    bot_logger.debug(f"❌ Elemento rejeitado: dentro de {indicator}")
                    return True
            except Exception:
                continue

        # Verificar distância do topo do post (comentários estão mais abaixo)
        try:
            post_container = elem.locator('xpath=ancestor::div[@role="article"]')
            if await post_container.count() > 0:
                post_box = await post_container.first().bounding_box()
                elem_box = await elem.bounding_box()

                if post_box and elem_box:
                    # Se o elemento está muito abaixo do início do post, pode ser comentário
                    distance_from_top = elem_box['y'] - post_box['y']
                    if distance_from_top > 300:  # Mais de 300px do topo do post
                        bot_logger.debug(f"❌ Elemento rejeitado: muito abaixo do topo do post ({distance_from_top}px)")
                        return True
        except Exception:
            pass

        # Verificar se o texto ao redor contém muitos indicadores de comentário
        try:
            context_text = await elem.locator('xpath=ancestor::*[3]').text_content()
            if context_text:
                comment_phrases = ['curtir', 'comentar', 'responder', 'like', 'reply', 'respond', 'compartilhar', 'share']
                phrase_count = sum(1 for phrase in comment_phrases if phrase in context_text.lower())

                # Se há muitas palavras de ação, provavelmente é área de comentário
                if phrase_count >= 3:
                    bot_logger.debug(f"❌ Elemento rejeitado: contexto com muitas ações de comentário ({phrase_count})")
                    return True
        except Exception:
            pass

        return False

    except Exception:
        return False

async def _extract_text(post: Locator) -> str:
    """Extrai texto do post usando inner_text e filtragem melhorada."""

    # Primeiro, tentar expandir texto
    try:
        see_more_selectors = [
            'div[role="button"]:has-text("Ver mais")',
            'div[role="button"]:has-text("See more")',
            '*[role="button"]:has-text("Ver mais")',
            '*[role="button"]:has-text("See more")'
        ]

        for selector in see_more_selectors:
            try:
                see_more_button = post.locator(selector).first()
                if await see_more_button.count() > 0 and await see_more_button.is_visible():
                    await see_more_button.click()
                    await asyncio.sleep(2)
                    break
            except Exception:
                continue

    except Exception:
        bot_logger.debug("Erro ao expandir texto")

    # Extrair texto usando inner_text em elementos principais
    try:
        text_elements = post.locator('div[dir="auto"]:visible')
        all_texts = []

        count = await text_elements.count()
        for i in range(count):
            elem = text_elements.nth(i)
            try:
                if await elem.is_visible():
                    # Usar inner_text para melhor extração
                    text = (await elem.inner_text() or "").strip()
                    if text and len(text) > 10:  # Linhas com mais de 10 caracteres
                        # Filtrar linhas de UI
                        lines = text.split('\n')
                        valid_lines = []

                        for line in lines:
                            line_clean = line.strip()
                            if (len(line_clean) > 10 and
                                re.search(r'[A-Za-zÀ-ÿ]', line_clean) and  # Contém letras
                                not any(ui_term in line_clean.lower() for ui_term in [
                                    'ver mais', 'see more', 'ver tradução', 'see translation',
                                    'like', 'comment', 'share', 'curtir', 'comentar', 'compartilhar'
                                ])):
                                valid_lines.append(line_clean)

                        if valid_lines:
                            all_texts.extend(valid_lines)

            except Exception:
                continue

        if all_texts:
            # Juntar textos válidos
            combined_text = '\n'.join(all_texts)
            combined_text = re.sub(r'\n{3,}', '\n\n', combined_text)  # Normalizar quebras
            combined_text = combined_text.strip()

            if len(combined_text) >= 8:
                bot_logger.debug(f"Texto extraído: {len(combined_text)} chars")
                return combined_text

    except Exception as e:
        bot_logger.debug(f"Erro na extração de texto: {e}")

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


async def has_video(post: Locator) -> bool:
    """Verifica se o post contém vídeo."""
    try:
        # Verificar elementos de vídeo
        video_selectors = [
            'video',
            '[data-video-id]',
            '[aria-label*="video" i]',
            '[aria-label*="vídeo" i]',
            'div[role="button"][aria-label*="play" i]'
        ]
        
        for selector in video_selectors:
            try:
                video_elements = post.locator(selector)
                if await video_elements.count() > 0:
                    return True
            except Exception:
                continue
        
        return False
    except Exception:
        return False