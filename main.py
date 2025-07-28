
import asyncio
import logging
from pathlib import Path
from typing import Optional
import threading

from logger import setup_logging, bot_logger
from state_manager import StateManager
from fb_bot.config import config
from fb_bot.login import fb_login
from fb_bot.monitor import extract_post_id, extract_post_details, iterate_posts
from fb_bot.commenter import open_comment_box, send_comment
from fb_bot.n8n_client import ask_n8n, healthcheck_n8n

# Global stop event for clean shutdown
stop_event = threading.Event()

class PostProcessor:
    """Processador de posts com logging limpo."""

    def __init__(self, state: StateManager):
        self.state = state
        self.posts_processed_session = 0
        self.leads_found_session = 0

    async def process_post(self, post_element, page) -> bool:
        """Processa um único post."""
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

        # Extrair detalhes com retry
        details = await self._extract_with_retry(post_element)
        if not details:
            self.state.add(post_id)
            return False

        # Validar conteúdo
        if not self._is_valid_post(details):
            self.state.add(post_id)
            return False

        # Verificar palavras-chave
        if not self._matches_keywords(details.get('text', '')):
            bot_logger.debug("Post filtrado - sem palavras-chave relevantes")
            self.state.add(post_id)
            return False

        # Lead encontrado!
        bot_logger.info(f"LEAD ENCONTRADO: {details.get('author', 'N/A')}")
        bot_logger.info(f"Texto: {details.get('text', '')[:100]}...")

        # Enviar para n8n com backoff exponencial
        reply = await self._get_ai_response_async(details, post_id)
        if not reply:
            self.state.add(post_id)
            return False

        # Comentar
        success = await self._send_comment(post_element, reply)
        self.state.add(post_id)

        if success:
            self.leads_found_session += 1
            bot_logger.info(f"Comentário enviado! Total de leads: {self.leads_found_session}")

        return success

    async def _extract_with_retry(self, post_element, max_retries: int = 2):
        """Extrai detalhes com retry limitado."""
        for attempt in range(max_retries + 1):
            try:
                details = await extract_post_details(post_element)
                if details and (details.get('text') or details.get('image_url') or details.get('has_video')):
                    return details
                    
                if attempt < max_retries:
                    bot_logger.debug(f"Tentativa {attempt + 1} falhou, aguardando...")
                    await asyncio.sleep(2)
                    
            except Exception as e:
                bot_logger.error(f"Erro na extração tentativa {attempt + 1}: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(2)
                    
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

    async def _get_ai_response_async(self, details: dict, post_id: str) -> Optional[str]:
        """Obtém resposta da IA com backoff exponencial."""
        payload = {
            "prompt": details.get('text', 'Post sem texto - apenas imagem'),
            "author": details.get('author', 'Autor não identificado'),
            "image_url": details.get('image_url', ''),
            "post_id": post_id
        }

        bot_logger.info("Enviando para IA...")
        
        # Retry com backoff exponencial
        max_retries = 3
        base_delay = 1
        
        for attempt in range(max_retries):
            try:
                reply = await ask_n8n(config.n8n_webhook_url, payload)
                if reply:
                    bot_logger.info(f"IA respondeu: {reply[:50]}...")
                    return reply
                    
            except Exception as e:
                bot_logger.error(f"Erro na tentativa {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)

        bot_logger.error("IA não respondeu após todas as tentativas")
        return None

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

    # Verificar n8n
    try:
        if not await healthcheck_n8n(config.n8n_webhook_url):
            bot_logger.error("n8n não está acessível")
            return
    except Exception as e:
        bot_logger.error(f"Erro ao verificar n8n: {e}")
        return

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

                # Processar posts
                posts_found = 0
                leads_found = 0

                bot_logger.debug("Iniciando processamento de posts...")
                
                # Usar max_posts_per_cycle da config
                async for post_element in iterate_posts(page, max_posts=config.max_posts_per_cycle):
                    if stop_event.is_set():
                        bot_logger.info("Stop event detectado, parando processamento")
                        break
                        
                    try:
                        if page.is_closed():
                            bot_logger.warning("Página fechada durante iteração - interrompendo")
                            break
                        
                        posts_found += 1
                        success = await processor.process_post(post_element, page)

                        if success:
                            leads_found += 1
                            bot_logger.debug("Pausa após comentário bem-sucedido")
                            await asyncio.sleep(15)
                        else:
                            await asyncio.sleep(3)
                            
                        # Verificação adicional de integridade da página
                        try:
                            await page.evaluate("() => window.location.href")
                        except Exception:
                            bot_logger.warning("Página não responde - interrompendo iteração")
                            break

                    except Exception as e:
                        bot_logger.error(f"Erro processando post: {e}")
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
