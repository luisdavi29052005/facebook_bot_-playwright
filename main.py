import asyncio
import logging
from pathlib import Path
from typing import Optional
import threading

from logger import setup_logging, bot_logger
from state_manager import StateManager
from fb_bot.config import config
from fb_bot.login import fb_login
from fb_bot.monitor import navigate_to_group, find_next_valid_post, extract_post_details, find_next_unprocessed_post, infer_post_key, extract_post_id
from fb_bot.commenter import open_comment_box, send_comment
from fb_bot.n8n_client import ask_n8n, healthcheck_n8n
from fb_bot.circuit_breaker import facebook_circuit_breaker, retry_with_backoff, RetryConfig

# Global stop event for clean shutdown
stop_event = threading.Event()

class PostProcessor:
    """Processador de posts com logging limpo."""

    def __init__(self, state: StateManager):
        self.state = state
        self.posts_processed_session = 0
        self.leads_found_session = 0

    async def process_post(self, post_element, page) -> bool:
        """Processa um único post com circuit breaker protection."""

        async def _process_post_core():
            # Check stop event
            if stop_event.is_set():
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
            details = await self._extract_with_retry(post_element)
            if not details:
                self.state.add(post_id)
                return False

            # Validar se n8n processou corretamente
            author = details.get('author', '').strip()
            text = details.get('text', '').strip()
            reply = details.get('reply', '').strip()

            if not author or not text or not reply:
                bot_logger.warning(f"Dados incompletos do n8n - autor:{bool(author)}, texto:{bool(text)}, reply:{bool(reply)}")
                self.state.add(post_id)
                return False

            # Verificar palavras-chave no texto extraído
            if not self._matches_keywords(text):
                bot_logger.debug("Post filtrado - sem palavras-chave relevantes")
                self.state.add(post_id)
                return False

            # Lead encontrado!
            bot_logger.info(f"LEAD ENCONTRADO: {author}")
            bot_logger.info(f"Texto: {text[:100]}...")
            bot_logger.info(f"Reply: {reply[:50]}...")

            # Comentar com reply do n8n
            success = await facebook_circuit_breaker.call(
                self._send_comment, post_element, reply
            )
            self.state.add(post_id)

            if success:
                self.leads_found_session += 1
                bot_logger.info(f"Comentário enviado! Total de leads: {self.leads_found_session}")

            return success

        try:
            return await _process_post_core()
        except Exception as e:
            bot_logger.error(f"Erro protegido por circuit breaker: {e}")
            return False

    async def _extract_with_retry(self, post_element, max_retries: int = 2):
        """Extrai detalhes via n8n com retry limitado."""
        for attempt in range(max_retries + 1):
            try:
                details = await extract_post_details(post_element, config.n8n_webhook_url)
                
                # Verificar se n8n retornou dados completos
                if (details and 
                    details.get('author') and 
                    details.get('text') and 
                    details.get('reply')):
                    return details

                if attempt < max_retries:
                    bot_logger.debug(f"Tentativa {attempt + 1} falhou, aguardando...")
                    await asyncio.sleep(3)

            except Exception as e:
                bot_logger.error(f"Erro na extração tentativa {attempt + 1}: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(3)

        return None

    def _is_valid_post(self, details: dict) -> bool:
        """Valida se o post tem conteúdo válido."""
        text = details.get('text', '').strip()
        image_url = details.get('image_url', '').strip()
        has_video = details.get('has_video', False)

        # Post deve ter texto, imagem ou vídeo
        if not text and not image_url and not has_video:
            return False

        # Verificar se autor não é timestamp ou elemento de UI
        author = details.get('author', '').strip()
        if author:
            import re
            invalid_patterns = [
                r'^\d+\s*(min|h|hr|hrs|d|dia|dias|hora|horas|s|sec|seconds)$',
                r'^\d+\s*(min|h|hr|hrs|d|dia|dias|hora|horas|s|sec|seconds)\s*(ago|atrás)?$',
                r'^(há|ago)\s+\d+',
                r'^(like|comment|share|curtir|comentar|compartilhar)$'
            ]
            if any(re.search(pattern, author.lower()) for pattern in invalid_patterns):
                bot_logger.warning(f"Autor inválido detectado: {author}")
                return False

        return True

    def _matches_keywords(self, text: str) -> bool:
        """Verifica se o texto contém palavras-chave."""
        if not config.keywords:
            return True

        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in config.keywords)

    

    async def _send_comment(self, post_element, comment: str) -> bool:
        """Envia comentário no post."""
        try:
            if await open_comment_box(post_element):
                return await send_comment(post_element, comment)
            return False
        except Exception as e:
            bot_logger.error(f"Erro ao comentar: {e}")
            return False

async def main_loop():
    """Loop principal com parada limpa."""
    setup_logging()
    bot_logger.info("Iniciando bot...")

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

    # Login
    bot_logger.info("Fazendo login no Facebook...")
    login_manager = await fb_login(headless=config.headless)
    if not login_manager:
        bot_logger.error("Falha no login")
        return

    page = login_manager.get_page()
    bot_logger.info("Login realizado com sucesso")

    # Loop principal
    consecutive_empty_cycles = 0

    try:
        while not stop_event.is_set():
            try:
                bot_logger.info("Iniciando novo ciclo...")

                # Verificar se página/contexto ainda estão ativos
                try:
                    if page.is_closed():
                        raise Exception("Página foi fechada")

                    if not login_manager.context.pages:
                        raise Exception("Contexto sem páginas")

                    # Teste simples para verificar se página responde
                    await page.evaluate("() => document.title")

                except Exception as e:
                    bot_logger.error(f"Sessão perdida: {e}")
                    bot_logger.info("Recriando sessão de login...")

                    # Limpar sessão anterior
                    try:
                        await login_manager.__aexit__(None, None, None)
                    except Exception:
                        pass

                    # Criar nova sessão
                    login_manager = await fb_login(headless=config.headless)
                    if not login_manager:
                        bot_logger.error("Falha ao recriar sessão")
                        break

                    page = login_manager.get_page()
                    bot_logger.info("Sessão recriada com sucesso")
                    await asyncio.sleep(3)

                # Navegar para grupo
                try:
                    await login_manager.navigate_to_group(config.facebook_group_url)
                except Exception as e:
                    bot_logger.error(f"Erro ao navegar para grupo: {e}")
                    continue

                # PROCESSAMENTO SEQUENCIAL COM DEDUPLICAÇÃO ROBUSTA
                posts_found = 0
                leads_found = 0
                seen_this_run = set()  # Chaves vistas nesta sessão
                consecutive_not_found = 0
                last_post_key = None
                key_repetition_count = 0

                bot_logger.info("🔄 Iniciando processamento sequencial com deduplicação...")

                # Loop sequencial: busca → screenshot → n8n processa → comenta → scroll → próximo
                for post_number in range(config.max_posts_per_cycle):
                    if stop_event.is_set():
                        bot_logger.info("Stop event detectado, parando processamento")
                        break

                    try:
                        if page.is_closed():
                            bot_logger.warning("Página fechada durante processamento - interrompendo")
                            break

                        # ═══ ETAPA 1: BUSCAR PRÓXIMO POST NÃO PROCESSADO ═══
                        bot_logger.info(f"🔍 Buscando post #{post_number + 1}/{config.max_posts_per_cycle}...")

                        # Combinar chaves já processadas (estado + sessão atual)
                        all_processed_keys = state._processed_ids.union(seen_this_run)

                        post_element = await find_next_unprocessed_post(page, all_processed_keys)

                        if not post_element:
                            consecutive_not_found += 1
                            bot_logger.warning(f"❌ Nenhum post não processado encontrado (tentativa {consecutive_not_found})")

                            if consecutive_not_found >= 2:
                                # Scroll mais agressivo para buscar conteúdo novo
                                bot_logger.debug("🔄 Tentando scroll agressivo para novos posts...")
                                try:
                                    for scroll_attempt in range(3):
                                        await page.mouse.wheel(0, 2000)
                                        await asyncio.sleep(3)

                                        post_element = await find_next_unprocessed_post(page, all_processed_keys)
                                        if post_element:
                                            bot_logger.debug(f"✅ Post encontrado após scroll agressivo {scroll_attempt + 1}")
                                            consecutive_not_found = 0
                                            break

                                    if not post_element:
                                        bot_logger.warning("❌ Nenhum post novo encontrado mesmo após scroll agressivo - finalizando ciclo")
                                        break

                                except Exception as e:
                                    bot_logger.warning(f"Erro durante scroll de recuperação: {e}")
                                    break
                            else:
                                # Tentativa simples de scroll
                                await page.mouse.wheel(0, 1200)
                                await asyncio.sleep(2)
                                continue

                        # Reset contador se encontrou post
                        consecutive_not_found = 0
                        posts_found += 1

                        # ═══ ETAPA 2: GERAR CHAVE ÚNICA DO POST ═══
                        post_key = await infer_post_key(post_element)
                        bot_logger.info(f"🔑 Chave do post: {post_key[:30]}...")

                        # Detectar se está preso no mesmo post
                        if post_key == last_post_key:
                            key_repetition_count += 1
                            bot_logger.warning(f"⚠️ Mesmo post detectado {key_repetition_count} vezes seguidas")

                            if key_repetition_count >= 3:
                                bot_logger.warning("🚨 Preso no mesmo post - forçando scroll e pulo")
                                await post_element.evaluate('el => el.setAttribute("data-processed", "true")')
                                await page.mouse.wheel(0, 2000)
                                await asyncio.sleep(3)
                                key_repetition_count = 0
                                continue
                        else:
                            key_repetition_count = 0
                            last_post_key = post_key

                        bot_logger.success(f"✅ POST #{post_number + 1} ENCONTRADO (novo) - iniciando processamento completo")

                        # ═══ ETAPA 3: PROCESSAR POST COMPLETAMENTE ═══
                        # Processamento sequencial: screenshot → n8n analisa → comentário
                        success = await processor.process_post(post_element, page)

                        # ═══ ETAPA 4: MARCAR COMO PROCESSADO ═══
                        if success:
                            # Só adiciona ao estado se processou com sucesso
                            state.add(post_key)
                            seen_this_run.add(post_key)

                            # Marcar no DOM para não reaparecer
                            try:
                                await post_element.evaluate('el => el.setAttribute("data-processed", "true")')
                                logger.debug("Post marcado como processado no DOM")
                            except Exception as e:
                                logger.debug(f"Erro ao marcar post no DOM: {e}")
                        else:
                            # Se falhou, não marca como processado para tentar novamente depois
                            logger.debug("Post não foi processado com sucesso, não marcando como processado")

                        # Scroll e pausa para próximo post
                        try:
                            await post_element.evaluate('el => el.setAttribute("data-processed", "true")')
                        except Exception:
                            pass

                        if success:
                            leads_found += 1
                            bot_logger.success(f"🎯 LEAD #{leads_found} PROCESSADO COM SUCESSO!")
                            bot_logger.info("⏸️ Aguardando 15s após comentário antes do próximo post...")
                            await asyncio.sleep(15)  # Pausa pós-comentário
                        else:
                            bot_logger.debug("⏸️ Post processado sem comentário - avançando...")
                            await asyncio.sleep(3)

                        # ═══ ETAPA 5: SCROLL PARA PRÓXIMO POST (APENAS APÓS PROCESSAMENTO COMPLETO) ═══
                        try:
                            # Scroll para "consumir" o post atual e revelar próximos
                            bot_logger.debug("📜 Fazendo scroll para próximo post...")
                            await page.mouse.wheel(0, 1200)
                            await asyncio.sleep(3)  # Aguardar novos posts carregarem
                        except Exception as e:
                            bot_logger.debug(f"Erro no scroll pós-processamento: {e}")

                        # Verificação de integridade da página
                        try:
                            await page.evaluate("() => window.location.href")
                        except Exception:
                            bot_logger.warning("❌ Página não responde - interrompendo ciclo")
                            break

                        bot_logger.info(f"✅ Post #{post_number + 1} TOTALMENTE CONCLUÍDO - avançando para próximo...")

                    except Exception as e:
                        bot_logger.error(f"❌ Erro crítico processando post #{post_number + 1}: {e}")

                        # Recuperação: scroll e continuar
                        try:
                            await page.mouse.wheel(0, 1500)
                            await asyncio.sleep(3)
                        except Exception:
                            pass

                        continue

                # Controle de ciclos vazios
                if posts_found == 0:
                    consecutive_empty_cycles += 1
                    bot_logger.warning(f"Ciclo vazio #{consecutive_empty_cycles}")

                    if consecutive_empty_cycles >= 3:
                        bot_logger.info("Muitos ciclos vazios - recarregando página")
                        await page.reload()
                        await asyncio.sleep(5)
                        consecutive_empty_cycles = 0
                else:
                    consecutive_empty_cycles = 0

                # Resumo do ciclo
                bot_logger.info(f"Ciclo concluído: {posts_found} posts, {leads_found} leads")

                # Aguardar próximo ciclo
                if not stop_event.is_set():
                    bot_logger.info(f"Aguardando {config.loop_interval_seconds}s...")
                    await asyncio.sleep(config.loop_interval_seconds)

            except asyncio.CancelledError:
                bot_logger.info("Loop cancelado")
                break
            except Exception as e:
                bot_logger.error(f"Erro no loop principal: {e}")
                if not stop_event.is_set():
                    await asyncio.sleep(30)

    finally:
        # Cleanup
        try:
            state.force_save()
            await login_manager.__aexit__(None, None, None)
            bot_logger.info("Bot encerrado")
        except Exception as e:
            bot_logger.error(f"Erro no encerramento: {e}")

def main():
    """Entrada principal."""
    asyncio.run(main_loop())

if __name__ == '__main__':
    main()