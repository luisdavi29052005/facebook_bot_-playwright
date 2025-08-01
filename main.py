
import asyncio
import logging
import multiprocessing
import signal
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import threading
import time

from logger import setup_logging, bot_logger
from state_manager import StateManager
from fb_bot.config import config
from fb_bot.login import fb_login
from fb_bot.monitor import navigate_to_group, find_next_valid_post, extract_post_details, find_next_unprocessed_post, infer_post_key, extract_post_id
from fb_bot.commenter import open_comment_box, send_comment
from fb_bot.n8n_client import ask_n8n, healthcheck_n8n
from fb_bot.circuit_breaker import facebook_circuit_breaker, retry_with_backoff, RetryConfig
from fb_bot.viewport_config import wait_for_page_stability, ensure_element_visible

# Global stop event for clean shutdown
stop_event = threading.Event()
# Global process reference for multiprocessing
bot_process: Optional[multiprocessing.Process] = None

class PostProcessor:
    """Processador de posts com logging limpo e verificações robustas."""

    def __init__(self, state: StateManager):
        self.state = state
        self.posts_processed_session = 0
        self.leads_found_session = 0

    async def process_post(self, post_element, page) -> bool:
        """Processa um único post com circuit breaker protection e verificações de estado."""

        async def _process_post_core():
            # Check stop event
            if stop_event.is_set():
                return False

            # Verificar se a página ainda está ativa
            if page.is_closed():
                bot_logger.error("Página foi fechada durante processamento do post")
                return False

            # Garantir visibilidade do elemento antes de processar
            bot_logger.debug("Garantindo visibilidade do post...")
            is_visible = await ensure_element_visible(page, post_element)
            if not is_visible:
                bot_logger.warning("Falha ao tornar post visível, pulando")
                return False

            # Extrair ID
            post_id = await extract_post_id(post_element)
            if not post_id:
                bot_logger.warning("Não foi possível extrair ID do post")
                return False

            # Verificar se já foi processado
            if self.state.has(post_id):
                bot_logger.debug(f"Post {post_id} já processado")
                return False

            # Extrair detalhes via n8n (screenshot → análise → reply)
            details = await self._extract_with_retry(post_element, page)
            if not details:
                self.state.add(post_id)
                return False

            # Validar se n8n processou corretamente
            author = details.get('author', '').strip()
            text = details.get('text', '').strip()
            reply = details.get('reply', '').strip()

            if not author and not text:
                bot_logger.warning(f"Post sem conteúdo detectável - ID: {post_id}")
                self.state.add(post_id)
                return False

            if not reply:
                bot_logger.warning(f"n8n não gerou resposta para post de {author}")
                self.state.add(post_id)
                return False

            # Se chegou aqui, é um lead válido
            bot_logger.success(f"🎯 LEAD DETECTADO: {author} | Resposta: {len(reply)} chars")

            # Tentar comentar
            try:
                # Verificar novamente se a página está ativa antes de comentar
                if page.is_closed():
                    bot_logger.error("Página fechada antes de comentar")
                    self.state.add(post_id)
                    return False

                await self._comment_with_retry(post_element, reply, page)
                self.leads_found_session += 1
                bot_logger.success(f"✅ Comentário enviado com sucesso!")

            except Exception as e:
                bot_logger.error(f"Erro ao comentar: {e}")

            # Marcar como processado independente do sucesso do comentário
            self.state.add(post_id)
            self.posts_processed_session += 1
            return True

        try:
            return await facebook_circuit_breaker.call(_process_post_core)
        except Exception as e:
            bot_logger.error(f"Erro no processamento do post: {e}")
            return False

    async def _extract_with_retry(self, post_element, page, max_retries=2) -> Optional[Dict[str, Any]]:
        """Extrai detalhes com retry e verificações de estado."""
        for attempt in range(max_retries):
            try:
                # Verificar estado da página antes de cada tentativa
                if page.is_closed():
                    bot_logger.error("Página fechada durante extração")
                    return None

                # Aguardar estabilidade antes de extrair
                await wait_for_page_stability(page, timeout=10000)

                details = await extract_post_details(post_element, config.n8n_webhook_url)
                if details and (details.get('author') or details.get('text')):
                    return details

                if attempt < max_retries - 1:
                    bot_logger.debug(f"Tentativa {attempt + 1} falhou, tentando novamente...")
                    await asyncio.sleep(2)

            except Exception as e:
                bot_logger.warning(f"Erro na extração (tentativa {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(3)

        return None

    async def _comment_with_retry(self, post_element, reply_text, page, max_retries=2):
        """Comenta com retry e verificações de estado."""
        for attempt in range(max_retries):
            try:
                # Verificar estado da página
                if page.is_closed():
                    raise Exception("Página fechada antes de comentar")

                # Garantir visibilidade novamente antes de comentar
                is_visible = await ensure_element_visible(page, post_element)
                if not is_visible:
                    raise Exception("Post não está visível para comentário")

                comment_box = await open_comment_box(post_element)
                if comment_box:
                    await send_comment(comment_box, reply_text)
                    return
                else:
                    raise Exception("Não foi possível abrir caixa de comentário")

            except Exception as e:
                if attempt < max_retries - 1:
                    bot_logger.warning(f"Erro ao comentar (tentativa {attempt + 1}): {e}")
                    await asyncio.sleep(3)
                else:
                    raise

async def main_loop():
    """Loop principal assíncrono com verificações robustas de estado."""
    setup_logging()
    bot_logger.info("🚀 Iniciando bot...")

    # Validar configurações
    is_valid, error_msg = config.is_valid()
    if not is_valid:
        bot_logger.error(f"Configuração inválida: {error_msg}")
        return

    # Verificar n8n apenas se configurado
    if config.n8n_webhook_url:
        try:
            if not await healthcheck_n8n(config.n8n_webhook_url):
                bot_logger.warning("n8n não está acessível - continuando sem processamento via n8n")
        except Exception as e:
            bot_logger.warning(f"Erro ao verificar n8n: {e} - continuando sem processamento via n8n")
    else:
        bot_logger.warning("n8n não configurado - screenshots não serão processados")

    # Inicializar
    state = StateManager()
    processor = PostProcessor(state)
    login_manager = None
    page = None

    try:
        # Login inicial
        bot_logger.info("Fazendo login no Facebook...")
        login_manager = await fb_login(headless=config.headless)
        if not login_manager:
            bot_logger.error("Falha no login")
            return

        page = login_manager.get_page()
        bot_logger.info("Login realizado com sucesso")

        # Loop principal
        consecutive_empty_cycles = 0

        while not stop_event.is_set():
            try:
                bot_logger.info("Iniciando novo ciclo...")

                # Verificar se página/contexto ainda estão ativos
                if not page or page.is_closed():
                    bot_logger.warning("Página fechada, tentando recriar sessão...")
                    
                    # Cleanup da sessão anterior
                    if login_manager:
                        try:
                            await login_manager.cleanup()
                        except Exception as e:
                            bot_logger.debug(f"Erro no cleanup: {e}")
                    
                    # Tentar novo login
                    login_manager = await fb_login(headless=config.headless)
                    if not login_manager:
                        bot_logger.error("Falha ao recriar sessão")
                        break
                    
                    page = login_manager.get_page()
                    bot_logger.info("Sessão recriada com sucesso")

                # Verificar se o contexto ainda tem páginas
                if not login_manager.context or not login_manager.context.pages:
                    raise Exception("Contexto do navegador perdido")

                # Log da URL atual para debug
                try:
                    current_url = page.url
                    bot_logger.debug(f"URL atual: {current_url}")
                except Exception as e:
                    bot_logger.warning(f"Não foi possível obter URL atual: {e}")

                # Navegar para o grupo
                bot_logger.info(f"Navegando para grupo: {config.facebook_group_url}")
                await navigate_to_group(page, config.facebook_group_url)

                # Aguardar estabilidade da página após navegação
                bot_logger.debug("Aguardando estabilidade da página...")
                await wait_for_page_stability(page, timeout=15000)

                # Log da URL após navegação
                try:
                    current_url = page.url
                    bot_logger.debug(f"URL após navegação: {current_url}")
                except Exception:
                    pass

                # Coletar chaves já processadas
                all_processed_keys = set(state.get_all_keys())
                bot_logger.info(f"📊 Processados na sessão: {processor.posts_processed_session} | Leads: {processor.leads_found_session}")

                # Processar posts
                posts_processed_cycle = 0
                consecutive_not_found = 0

                while posts_processed_cycle < config.max_posts_per_cycle and not stop_event.is_set():
                    try:
                        # Verificar estado da página antes de buscar posts
                        if page.is_closed():
                            bot_logger.error("Página fechada durante busca de posts")
                            break

                        post_element = await find_next_unprocessed_post(page, all_processed_keys)

                        if not post_element:
                            consecutive_not_found += 1
                            bot_logger.warning(f"❌ Nenhum post não processado encontrado (tentativa {consecutive_not_found})")

                            if consecutive_not_found >= 2:
                                # Scroll mais agressivo para buscar conteúdo novo
                                bot_logger.debug("🔄 Tentando scroll agressivo para novos posts...")
                                try:
                                    if not page.is_closed():
                                        for scroll_attempt in range(3):
                                            await page.mouse.wheel(0, 2000)
                                            await asyncio.sleep(3)

                                            post_element = await find_next_unprocessed_post(page, all_processed_keys)
                                            if post_element:
                                                bot_logger.debug(f"✅ Post encontrado após scroll agressivo {scroll_attempt + 1}")
                                                consecutive_not_found = 0
                                                break
                                    else:
                                        bot_logger.error("Página fechada durante scroll")
                                        break

                                    if not post_element:
                                        bot_logger.warning("❌ Nenhum post novo encontrado após scroll agressivo")
                                        break
                                except Exception as e:
                                    if "Target page" in str(e) and "has been closed" in str(e):
                                        bot_logger.error("Target page fechada durante scroll")
                                        break
                                    else:
                                        bot_logger.warning(f"Erro durante scroll: {e}")
                                        break
                            else:
                                break

                        if post_element:
                            consecutive_not_found = 0

                            # Processar post com verificações de estado
                            success = await processor.process_post(post_element, page)
                            if success:
                                posts_processed_cycle += 1

                            # Adicionar chave processada ao conjunto local
                            try:
                                post_key = await infer_post_key(post_element)
                                all_processed_keys.add(post_key)
                            except Exception as e:
                                bot_logger.debug(f"Erro ao adicionar chave processada: {e}")

                            # Delay entre posts para parecer mais humano
                            await asyncio.sleep(2)

                    except Exception as e:
                        if "Target page" in str(e) and "has been closed" in str(e):
                            bot_logger.error("Target page fechada durante processamento")
                            break
                        else:
                            bot_logger.error(f"Erro no processamento: {e}")
                            break

                # Estatísticas do ciclo
                if posts_processed_cycle == 0:
                    consecutive_empty_cycles += 1
                    bot_logger.warning(f"⚠️  Ciclo vazio #{consecutive_empty_cycles}")

                    if consecutive_empty_cycles >= 3:
                        bot_logger.warning("Muitos ciclos vazios, aumentando intervalo...")
                        await asyncio.sleep(min(config.loop_interval_seconds * 2, 600))
                        consecutive_empty_cycles = 0
                else:
                    consecutive_empty_cycles = 0
                    bot_logger.success(f"✅ Ciclo concluído: {posts_processed_cycle} posts processados")

            except Exception as e:
                if "Target page" in str(e) and "has been closed" in str(e):
                    bot_logger.error("Target page fechada, tentando recriar sessão no próximo ciclo")
                    page = None  # Forçar recriação na próxima iteração
                else:
                    bot_logger.error(f"Erro no ciclo: {e}")

            # Intervalo entre ciclos
            if not stop_event.is_set():
                bot_logger.info(f"⏱️  Aguardando {config.loop_interval_seconds}s até próximo ciclo...")
                await asyncio.sleep(config.loop_interval_seconds)

    except KeyboardInterrupt:
        bot_logger.info("Interrupção do usuário (Ctrl+C)")
    except Exception as e:
        bot_logger.error(f"Erro crítico no loop principal: {e}")
    finally:
        # Cleanup
        if login_manager:
            try:
                await login_manager.cleanup()
                bot_logger.info("Cleanup realizado")
            except Exception as e:
                bot_logger.debug(f"Erro no cleanup final: {e}")

        bot_logger.info(f"🏁 Bot finalizado. Processados: {processor.posts_processed_session} | Leads: {processor.leads_found_session}")

def run_bot_process():
    """Executa o bot em um processo separado."""
    try:
        # Configurar signal handlers para shutdown limpo
        def signal_handler(signum, frame):
            bot_logger.info(f"Recebido sinal {signum}, parando bot...")
            stop_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Executar loop principal
        asyncio.run(main_loop())
    except Exception as e:
        bot_logger.error(f"Erro no processo do bot: {e}")
    finally:
        bot_logger.info("Processo do bot finalizado")

def start_bot():
    """Inicia o bot em um processo separado."""
    global bot_process
    
    if bot_process and bot_process.is_alive():
        bot_logger.warning("Bot já está rodando")
        return False

    try:
        stop_event.clear()
        bot_process = multiprocessing.Process(target=run_bot_process)
        bot_process.start()
        bot_logger.info("Bot iniciado em processo separado")
        return True
    except Exception as e:
        bot_logger.error(f"Erro ao iniciar bot: {e}")
        return False

def stop_bot():
    """Para o bot de forma limpa."""
    global bot_process
    
    try:
        stop_event.set()
        
        if bot_process and bot_process.is_alive():
            bot_logger.info("Parando bot...")
            
            # Tentar parada limpa primeiro
            bot_process.join(timeout=10)
            
            if bot_process.is_alive():
                bot_logger.warning("Bot não parou graciosamente, forçando término...")
                bot_process.terminate()
                bot_process.join(timeout=5)
                
                if bot_process.is_alive():
                    bot_logger.error("Forçando kill do processo...")
                    bot_process.kill()
                    bot_process.join()
            
            bot_logger.info("Bot parado com sucesso")
            return True
        else:
            bot_logger.info("Bot não está rodando")
            return True
            
    except Exception as e:
        bot_logger.error(f"Erro ao parar bot: {e}")
        return False

def is_bot_running():
    """Verifica se o bot está rodando."""
    global bot_process
    return bot_process and bot_process.is_alive()

# Compatibilidade com código existente
async def main():
    """Compatibilidade - usa o novo main_loop."""
    await main_loop()

if __name__ == "__main__":
    start_bot()
    
    try:
        while is_bot_running():
            time.sleep(1)
    except KeyboardInterrupt:
        bot_logger.info("Interrupção detectada, parando bot...")
        stop_bot()
