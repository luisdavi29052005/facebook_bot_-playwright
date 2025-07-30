
import asyncio
import logging
from playwright.async_api import Page

logger = logging.getLogger(__name__)

# Configurações otimizadas de viewport para Facebook
VIEWPORT_CONFIGS = {
    "desktop_standard": {"width": 1366, "height": 768},
    "desktop_hd": {"width": 1440, "height": 900},
    "desktop_fhd": {"width": 1920, "height": 1080},
    "laptop": {"width": 1280, "height": 720}
}

# Configuração padrão recomendada
DEFAULT_VIEWPORT = VIEWPORT_CONFIGS["desktop_hd"]

async def setup_optimal_viewport(page: Page, config_name: str = "desktop_hd") -> None:
    """
    Configura viewport otimizado para extração do Facebook.
    
    Args:
        page: Página do Playwright
        config_name: Nome da configuração de viewport
    """
    try:
        viewport_config = VIEWPORT_CONFIGS.get(config_name, DEFAULT_VIEWPORT)
        
        # Definir viewport
        await page.set_viewport_size(
            width=viewport_config["width"], 
            height=viewport_config["height"]
        )
        
        # Garantir zoom 100%
        await page.evaluate("document.body.style.zoom = '1.0'")
        
        # Configurar CSS para melhor visibilidade
        await page.add_style_tag(content="""
            /* Melhorar visibilidade de posts */
            body {
                zoom: 1.0 !important;
                transform: scale(1.0) !important;
            }
            
            /* Garantir que posts sejam visíveis */
            [role="article"] {
                min-height: 100px !important;
                visibility: visible !important;
                opacity: 1 !important;
            }
            
            /* Evitar elementos colapsados */
            div[data-ad-rendering-role="story_message"] {
                min-height: 50px !important;
            }
        """)
        
        logger.debug(f"✅ Viewport configurado: {viewport_config['width']}x{viewport_config['height']}")
        
    except Exception as e:
        logger.warning(f"Erro ao configurar viewport: {e}")

async def ensure_element_visible(page: Page, element, scroll_behavior: str = "smooth") -> bool:
    """
    Garante que um elemento esteja visível na tela antes de operações.
    
    Args:
        page: Página do Playwright
        element: Elemento a ser tornado visível
        scroll_behavior: Comportamento do scroll ('smooth' ou 'auto')
        
    Returns:
        True se elemento estiver visível, False caso contrário
    """
    try:
        # Scroll para o elemento
        await element.scroll_into_view_if_needed()
        
        # Aguardar renderização
        await asyncio.sleep(0.7)
        
        # Verificar se está realmente visível
        is_visible = await element.is_visible()
        
        if not is_visible:
            # Tentar scroll manual
            logger.debug("Elemento não visível - tentando scroll manual")
            
            bbox = await element.bounding_box()
            if bbox:
                # Scroll para posição do elemento
                await page.evaluate(f"""
                    window.scrollTo({{
                        top: {bbox['y'] - 100},
                        behavior: '{scroll_behavior}'
                    }});
                """)
                
                await asyncio.sleep(1)
                is_visible = await element.is_visible()
        
        # Verificar se está no viewport
        if is_visible:
            viewport_size = page.viewport_size
            bbox = await element.bounding_box()
            
            if bbox and viewport_size:
                # Verificar se elemento está dentro do viewport
                in_viewport = (
                    bbox['x'] >= 0 and 
                    bbox['y'] >= 0 and
                    bbox['x'] + bbox['width'] <= viewport_size['width'] and
                    bbox['y'] + bbox['height'] <= viewport_size['height']
                )
                
                if not in_viewport:
                    logger.debug("Elemento fora do viewport - reposicionando")
                    
                    # Centralizar elemento no viewport
                    center_y = bbox['y'] + bbox['height'] / 2
                    scroll_to = center_y - viewport_size['height'] / 2
                    
                    await page.evaluate(f"""
                        window.scrollTo({{
                            top: {scroll_to},
                            behavior: '{scroll_behavior}'
                        }});
                    """)
                    
                    await asyncio.sleep(1)
        
        # Verificação final
        final_visibility = await element.is_visible()
        
        if final_visibility:
            logger.debug("✅ Elemento visível e pronto")
        else:
            logger.warning("⚠️ Elemento ainda não visível após tentativas")
            
        return final_visibility
        
    except Exception as e:
        logger.warning(f"Erro ao garantir visibilidade do elemento: {e}")
        return False

async def optimize_page_for_extraction(page: Page) -> None:
    """
    Otimiza a página para melhor extração de posts.
    
    Args:
        page: Página do Playwright
    """
    try:
        # Desabilitar animações para performance
        await page.add_style_tag(content="""
            *, *::before, *::after {
                animation-duration: 0.01ms !important;
                animation-delay: 0.01ms !important;
                transition-duration: 0.01ms !important;
                transition-delay: 0.01ms !important;
            }
        """)
        
        # Melhorar contraste e visibilidade
        await page.add_style_tag(content="""
            /* Melhorar visibilidade de textos */
            [role="article"] {
                background: white !important;
                border: 1px solid #e4e6ea !important;
                margin-bottom: 16px !important;
            }
            
            /* Destacar elementos importantes */
            h3, h2, strong {
                font-weight: bold !important;
                color: #1c1e21 !important;
            }
            
            /* Garantir que imagens sejam carregadas */
            img {
                opacity: 1 !important;
                visibility: visible !important;
            }
        """)
        
        # Aguardar aplicação dos estilos
        await asyncio.sleep(0.5)
        
        logger.debug("✅ Página otimizada para extração")
        
    except Exception as e:
        logger.warning(f"Erro ao otimizar página: {e}")

async def wait_for_page_stability(page: Page, timeout: int = 10000) -> bool:
    """
    Aguarda a página ficar estável para operações.
    
    Args:
        page: Página do Playwright
        timeout: Timeout em millisegundos
        
    Returns:
        True se página estiver estável, False caso contrário
    """
    try:
        # Aguardar rede ficar ociosa
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            logger.debug("Timeout networkidle - continuando")
        
        # Aguardar elementos de post aparecerem
        try:
            await page.wait_for_selector('[role="article"]', timeout=5000)
        except Exception:
            logger.debug("Posts não encontrados no timeout")
        
        # Verificar se há esqueletos de carregamento
        skeleton_gone = False
        for attempt in range(10):  # 10 tentativas de 500ms
            try:
                skeletons = page.locator('[data-visualcompletion="loading-state"]:visible')
                skeleton_count = await skeletons.count()
                
                if skeleton_count == 0:
                    skeleton_gone = True
                    break
                    
                logger.debug(f"Aguardando {skeleton_count} skeletons desaparecerem...")
                await asyncio.sleep(0.5)
                
            except Exception:
                break
        
        if skeleton_gone:
            logger.debug("✅ Página estável - skeletons removidos")
        else:
            logger.debug("⚠️ Alguns skeletons ainda presentes")
        
        return True
        
    except Exception as e:
        logger.warning(f"Erro ao aguardar estabilidade da página: {e}")
        return False
