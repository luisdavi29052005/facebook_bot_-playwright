
# main.py
import asyncio
import logging
import json
import re
from pathlib import Path

# Módulos do projeto
from logger import setup_logging
from state_manager import StateManager
from fb_bot.config import N8N_WEBHOOK_URL, FB_GROUP_URL, HEADLESS, LOOP_INTERVAL_SECONDS, KEYWORDS
from fb_bot.login import fb_login
from fb_bot.monitor import extract_post_details, extract_post_id, find_next_valid_post
from fb_bot.commenter import open_comment_box, send_comment
from fb_bot.n8n_client import ask_n8n, healthcheck_n8n

async def process_single_post(post_element, page, state: StateManager):
    """Processa um único post, desde a extração até o comentário."""

    # Extrair ID do post
    post_id = await extract_post_id(post_element)

    # Debug: Mostrar preview do post
    try:
        post_preview = (await post_element.text_content() or "")[:100]
        logging.info(f"📝 Preview do post: {post_preview if post_preview else 'Não foi possível extrair texto'}")
    except Exception:
        logging.info(f"📝 Preview do post: Erro ao extrair preview")

    logging.info(f"🔑 ID do post extraído: {post_id}")

    if not post_id:
        logging.warning("❌ FALHOU: Não foi possível extrair ID do post")
        return False

    if state.has(post_id):
        logging.info(f"⏭️ IGNORADO: Post {post_id} já foi processado anteriormente")
        return False

    # Extrair detalhes do post
    logging.info("🔍 EXTRAÇÃO: Iniciando extração de detalhes do post...")
    try:
        details = await extract_post_details(post_element)
        
        # VALIDAÇÃO RIGOROSA DOS DADOS EXTRAÍDOS
        author = details.get('author', '')
        text = details.get('text', '')
        image_url = details.get('image_url', '')
        
        logging.info("🔍 VALIDAÇÃO RIGOROSA DOS DADOS EXTRAÍDOS:")
        logging.info("=" * 80)
        
        # Validar AUTOR com padrões mais rigorosos
        logging.info(f"👤 AUTOR EXTRAÍDO: '{author}' ({len(author)} chars)")
        
        # Padrões de timestamp mais abrangentes
        timestamp_patterns = [
            r'^\d+\s*(h|hr|hrs|min|mins|m|d|dia|dias|hora|horas|s|sec|seconds)$',
            r'^\d+\s*(h|hr|hrs|min|mins|m|d|dia|dias|hora|horas|s|sec)\s*(ago|atrás)?$',
            r'^(há|ago)\s+\d+',
            r'^\d+\s*[hmdHMD]$',
            r'^\d{1,2}[hmd]$',
        ]
        
        # Padrões de UI elements
        ui_patterns = [
            r'^(Like|Comment|Share|Curtir|Comentar|Compartilhar|Reply|Responder)$',
            r'^(Follow|Seguir|See More|Ver Mais|Most Relevant|Top Contributor)$',
            r'^(Author|Admin|Moderator)$',
            r'^·$',
            r'^\d+$',
        ]
        
        if author:
            is_timestamp = any(re.search(pattern, author, re.IGNORECASE) for pattern in timestamp_patterns)
            is_ui_element = any(re.search(pattern, author, re.IGNORECASE) for pattern in ui_patterns)
            
            if is_timestamp:
                logging.error(f"❌ ERRO CRÍTICO: Autor é timestamp: '{author}'")
                logging.error("❌ REGRA VIOLADA: Autor deve ser nome real do perfil/página")
                logging.error("💡 SOLUÇÃO: Melhorar seletores de extração de autor")
                
                # Falhar a extração se autor for timestamp
                logging.error("🚫 EXTRAÇÃO FALHADA: Dados inválidos detectados")
                return False
                
            elif is_ui_element:
                logging.error(f"❌ ERRO CRÍTICO: Autor é elemento de interface: '{author}'")
                logging.error("❌ REGRA VIOLADA: Autor não pode ser botão/link de UI")
                logging.error("💡 SOLUÇÃO: Melhorar seletores para evitar elementos de UI")
                
                # Falhar a extração se autor for elemento de UI
                logging.error("🚫 EXTRAÇÃO FALHADA: Dados inválidos detectados")
                return False
                
            elif len(author) < 2:
                logging.error(f"❌ ERRO: Autor muito curto: '{author}'")
                logging.error("💡 SOLUÇÃO: Nome de autor deve ter pelo menos 2 caracteres")
                return False
                
            else:
                logging.info(f"✅ AUTOR VÁLIDO: '{author}' (nome real identificado)")
        else:
            logging.warning("⚠️ ATENÇÃO: Nenhum autor identificado")
            logging.warning("💡 Continuando pois pode ser post anônimo...")
        
        # Validar TEXTO com verificações mais rigorosas
        logging.info(f"📝 TEXTO EXTRAÍDO: {len(text)} caracteres")
        if text:
            # Verificar se texto não é apenas elementos de interface
            ui_indicators = [
                'like', 'comment', 'share', 'curtir', 'comentar', 'compartilhar',
                'reply', 'responder', 'follow', 'seguir', 'see more', 'ver mais'
            ]
            text_lower = text.lower()
            
            # Se texto é muito curto e contém apenas UI elements
            if len(text) < 30 and any(ui in text_lower for ui in ui_indicators):
                logging.warning(f"⚠️ ATENÇÃO: Texto parece conter apenas elementos de interface")
                logging.warning(f"📄 Conteúdo suspeito: '{text}'")
                # Não falhar, apenas avisar
            else:
                logging.info(f"✅ TEXTO VÁLIDO: Conteúdo principal identificado")
                logging.info(f"📄 TEXTO COMPLETO: {text}")
                
        else:
            logging.info("📄 TEXTO: Vazio (post pode ser apenas imagem)")
        
        # Validar IMAGEM
        if image_url:
            logging.info(f"✅ IMAGEM ENCONTRADA: {image_url[:150]}...")
            
            # Verificar se não é avatar/emoji/static
            invalid_img_indicators = ['profile', 'avatar', 'emoji', 'static', 'icon', 'badge']
            is_invalid_img = any(indicator in image_url.lower() for indicator in invalid_img_indicators)
            
            if is_invalid_img:
                logging.warning("⚠️ ATENÇÃO: Imagem pode ser avatar/emoji (não conteúdo principal)")
                logging.warning(f"🔗 URL suspeita: {image_url[:100]}...")
            else:
                logging.info("✅ IMAGEM VÁLIDA: Conteúdo principal do post")
        else:
            logging.info("🖼️ IMAGEM: Não encontrada")
        
        logging.info("=" * 80)
        
        # Log de referência para dados corretos
        logging.info("📋 REFERÊNCIA - DADOS CORRETOS:")
        logging.info('   ✅ Autor correto: "João Silva", "Maria Santos", "Empresa XYZ"')
        logging.info('   ✅ Texto correto: Conteúdo real do post do usuário')
        logging.info('   ✅ Imagem correta: URL do scontent.xx.fbcdn.net')
        logging.info("")
        logging.info("📋 DADOS INCORRETOS (NUNCA DEVE APARECER):")
        logging.info('   ❌ Autor incorreto: "2h", "5min", "há 3 dias", "Like", "Comment"')
        logging.info('   ❌ Texto incorreto: "Like Comment Share", elementos de UI')
        logging.info('   ❌ Imagem incorreta: URLs de profile, emoji, static')
        logging.info("=" * 80)
        
    except Exception as e:
        logging.error(f"❌ FALHOU na extração de detalhes: {e}")
        logging.exception("Stack trace completo:")
        return False

    # Validação do conteúdo
    if not details.get('text') and not details.get('image_url'):
        logging.info(f"📭 FILTRADO: Post sem conteúdo de texto ou imagem")
        state.add(post_id)
        return False

    # Validação por palavra-chave (apenas se houver texto)
    if details.get('text'):
        text_lower = details['text'].lower()
        matching_keywords = [k for k in KEYWORDS if k.lower() in text_lower]

        if not matching_keywords:
            logging.info(f"🔍 FILTRADO: Post não contém palavras-chave relevantes")
            logging.info(f"🔑 Palavras-chave procuradas: {KEYWORDS}")
            state.add(post_id)
            return False
        else:
            logging.info(f"🎯 APROVADO: Post contém palavras-chave: {matching_keywords}")

    # Se passou nos filtros, é um lead!
    logging.info("🚨" * 50)
    logging.info("🚨 🎯 LEAD QUALIFICADO ENCONTRADO! 🎯")
    logging.info("🚨 INICIANDO PROCESSAMENTO AUTOMÁTICO COMPLETO")
    logging.info("🚨" * 50)
    logging.info(f"🆔 ID ÚNICO DO POST: {post_id}")
    logging.info(f"👤 AUTOR IDENTIFICADO: '{details.get('author', 'Não identificado')}'")
    logging.info(f"📝 CONTEÚDO DE TEXTO: {len(details.get('text', ''))} caracteres")
    if details.get('text'):
        logging.info(f"📄 TEXTO COMPLETO DO POST:")
        logging.info(f"    {details.get('text')}")
        matching_keywords = [k for k in KEYWORDS if k.lower() in details['text'].lower()]
        logging.info(f"🔑 PALAVRAS-CHAVE RELEVANTES ENCONTRADAS: {matching_keywords}")
        logging.info(f"📊 Total de palavras-chave correspondentes: {len(matching_keywords)}")
    else:
        logging.info("📄 CONTEÚDO: Post é apenas imagem (sem texto)")
    if details.get('image_url'):
        logging.info(f"🖼️ IMAGEM DE CONTEÚDO DETECTADA")
        logging.info(f"🔗 URL DA IMAGEM: {details['image_url']}")
    logging.info("🚨" * 50)

    # PASSO 1: Enviar para n8n
    logging.info("🚀" * 30)
    logging.info("🚀 PASSO 1: ENVIANDO DADOS PARA INTELIGÊNCIA ARTIFICIAL")
    logging.info("🚀" * 30)
    logging.info(f"🌐 Endpoint N8N: {N8N_WEBHOOK_URL}")
    logging.info(f"👤 AUTOR DO POST: '{details.get('author')}'")
    logging.info(f"📄 TEXTO PARA ANÁLISE: {len(details.get('text', ''))} caracteres")
    logging.info(f"🖼️ IMAGEM INCLUÍDA: {'Sim' if details.get('image_url') else 'Não'}")
    
    # Preparar dados para envio
    n8n_payload = {
        "prompt": details.get('text', 'Post sem texto - apenas imagem'),
        "author": details.get('author', 'Autor não identificado'),
        "image_url": details.get('image_url', ''),
        "post_id": post_id
    }
    
    logging.info("📦 PAYLOAD PREPARADO PARA ENVIO:")
    logging.info(f"   📝 Prompt: {n8n_payload['prompt'][:100]}..." if len(n8n_payload['prompt']) > 100 else f"   📝 Prompt: {n8n_payload['prompt']}")
    logging.info(f"   👤 Autor: {n8n_payload['author']}")
    logging.info(f"   🖼️ URL da imagem: {'Incluída' if n8n_payload['image_url'] else 'Nenhuma'}")
    logging.info(f"   🆔 Post ID: {n8n_payload['post_id']}")
    
    logging.info("⏳ Enviando requisição para N8N... Aguardando resposta da IA...")
    reply = ask_n8n(N8N_WEBHOOK_URL, n8n_payload)

    if not reply:
        logging.error("❌ PASSO 1 FALHOU: N8N não retornou resposta")
        logging.error("🔴 Possíveis causas: n8n offline, webhook incorreto, erro na IA")
        logging.error("📝 Marcando como processado para evitar loop infinito")
        state.add(post_id)
        return False

    logging.info("✅" * 30)
    logging.info("✅ PASSO 1 CONCLUÍDO COM SUCESSO!")
    logging.info("✅ RESPOSTA DA INTELIGÊNCIA ARTIFICIAL RECEBIDA")
    logging.info("✅" * 30)
    logging.info(f"🤖 RESPOSTA GERADA PELA IA:")
    logging.info(f"💬 CONTEÚDO: {reply}")
    logging.info(f"📏 TAMANHO DA RESPOSTA: {len(reply)} caracteres")
    logging.info(f"📊 QUALIDADE: {'✅ Adequada' if len(reply) > 20 else '⚠️ Muito curta'}")

    # PASSO 2: Comentar no post
    logging.info("💬" * 30)
    logging.info("💬 PASSO 2: POSTANDO COMENTÁRIO AUTOMÁTICO")
    logging.info("💬" * 30)
    logging.info(f"🎯 PREPARANDO PARA COMENTAR NO POST DO AUTOR: '{details.get('author')}'")
    logging.info(f"✍️ COMENTÁRIO QUE SERÁ POSTADO: {reply}")
    try:
        if await open_comment_box(post_element):
            if await send_comment(post_element, reply):
                logging.info("✅ PASSO 2 SUCESSO: Comentário enviado!")
                logging.info(f"📝 COMENTÁRIO: {reply}")
                state.add(post_id)
                
                # Log final de sucesso
                logging.info("🎉" * 50)
                logging.info("🎉 🌟 MISSÃO CUMPRIDA COM SUCESSO TOTAL! 🌟")
                logging.info("🎉 LEAD PROCESSADO E COMENTÁRIO ENVIADO!")
                logging.info("🎉" * 50)
                logging.info(f"✅ RESULTADO FINAL:")
                logging.info(f"   👤 Autor do post: {details.get('author')}")
                logging.info(f"   💬 Comentário enviado: {reply}")
                logging.info(f"   📊 Caracteres do comentário: {len(reply)}")
                logging.info(f"   🆔 Post processado: {post_id}")
                logging.info(f"   ⏰ Processo concluído com sucesso!")
                logging.info("🎉" * 50)
                return True
            else:
                logging.error("❌ PASSO 2 FALHOU: Erro ao enviar comentário")
                state.add(post_id)
                return False
        else:
            logging.error("❌ PASSO 2 FALHOU: Não foi possível abrir caixa de comentários")
            state.add(post_id)
            return False
    except Exception as e:
        logging.error(f"❌ PASSO 2 FALHOU: Erro inesperado ao comentar: {e}")
        state.add(post_id)
        return False

async def main_loop():
    """Função principal que orquestra todo o processo do bot."""
    try:
        setup_logging()
        logging.info("🚀 Iniciando main_loop assíncrono...")

        # Verificar configurações essenciais
        if not N8N_WEBHOOK_URL:
            logging.critical("❌ N8N_WEBHOOK_URL não configurado. Verifique o arquivo .env")
            return

        if not FB_GROUP_URL:
            logging.critical("❌ FACEBOOK_GROUP_URL não configurado. Verifique o arquivo .env")
            return

        logging.info(f"🔗 URL do n8n: {N8N_WEBHOOK_URL}")
        logging.info(f"🔗 URL do grupo: {FB_GROUP_URL}")

        if not healthcheck_n8n(N8N_WEBHOOK_URL):
            logging.critical("❌ Health check do n8n falhou. Verifique se o n8n está rodando e o webhook está ativo. Encerrando.")
            return

        state = StateManager()
        
        # Login com Playwright usando sessão persistente
        logging.info("🔐 Iniciando login com Playwright (sessão persistente)...")
        
        # Verificar se cookies.json existe
        cookies_path = Path("./cookies.json")
        if cookies_path.exists():
            logging.info("🍪 Arquivo cookies.json encontrado - tentará login automático com cookies")
            with open(cookies_path, 'r') as f:
                cookies_data = json.load(f)
                if isinstance(cookies_data, dict):
                    cookies_count = len(cookies_data.get('all', cookies_data.get('essential', cookies_data)))
                else:
                    cookies_count = len(cookies_data) if isinstance(cookies_data, list) else 0
                logging.info(f"🍪 {cookies_count} cookies carregados do arquivo")
        else:
            logging.warning("⚠️ Arquivo cookies.json não encontrado - será necessário login manual")
            
        logging.info("💡 NOVA FUNCIONALIDADE: Sessão do Facebook será mantida entre execuções!")
        logging.info("📁 Diretório de sessão: ./sessions/facebook_profile")
        
        login_manager = await fb_login(headless=HEADLESS)
        if not login_manager:
            logging.critical("❌ Falha crítica no login. Encerrando o bot.")
            return

        page = login_manager.get_page()
        logging.info("✅ Bot iniciado com sucesso usando sessão persistente!")
        logging.info("🔄 Próximas execuções não precisarão de login manual!")
    
    # Variáveis para controle do estado de navegação
        posts_processed_in_session = 0
        consecutive_empty_cycles = 0
        
        while True:
            try:
                await login_manager.navigate_to_group(FB_GROUP_URL)
                
                # FLUXO SISTEMÁTICO: Processar posts do topo para baixo
                logging.info("🎯 INICIANDO PROCESSAMENTO SISTEMÁTICO DO FEED")
                logging.info("🔝 Sempre começando do topo do feed do grupo")
                
                # PASSO 1: Scroll para o topo e aguardar carregamento
                logging.info("⬆️ PASSO 1: Fazendo scroll para o topo do feed")
                await page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(3)
                
                # Aguardar feed carregar completamente
                try:
                    await page.wait_for_selector("div[role='feed']", timeout=10000)
                    logging.info("✅ Feed carregado completamente")
                except Exception:
                    logging.warning("⚠️ Timeout aguardando feed")
                
                # PASSO 2: Identificar TODOS os posts visíveis no feed
                logging.info("🔍 PASSO 2: Identificando todos os posts visíveis no feed")
                
                posts_found_in_cycle = 0
                new_leads_found = 0
                current_post_index = 0
                max_posts_per_cycle = 15
                
                while current_post_index < max_posts_per_cycle:
                    try:
                        logging.info("=" * 80)
                        logging.info(f"📋 PROCESSANDO POST #{current_post_index + 1}")
                        logging.info("=" * 80)
                        
                        # PASSO 3: Buscar o próximo post válido
                        logging.info(f"🔍 PASSO 3: Buscando post na posição {current_post_index}")
                        post_element = await find_next_valid_post(page, current_post_index)
                        
                        if not post_element:
                            logging.info(f"❌ Nenhum post encontrado na posição {current_post_index}")
                            # Tentar fazer scroll para carregar mais posts
                            if current_post_index > 0:
                                logging.info("📜 Tentando carregar mais posts...")
                                try:
                                    await page.evaluate("window.scrollBy(0, 300)")
                                    await asyncio.sleep(2)
                                except Exception:
                                    await asyncio.sleep(2)
                                
                                # Tentar novamente após scroll
                                post_element = await find_next_valid_post(page, current_post_index)
                                
                            if not post_element:
                                logging.info("❌ Não há mais posts disponíveis")
                                break
                        
                        posts_found_in_cycle += 1
                        
                        # PASSO 4: Centralizar post e aguardar carregamento completo
                        logging.info("⏳ PASSO 4: Centralizando post e aguardando carregamento...")
                        try:
                            await post_element.scroll_into_view_if_needed()
                            await asyncio.sleep(2)
                            
                            # Verificar se o post está completamente visível
                            if await post_element.is_visible():
                                bbox = await post_element.bounding_box()
                                if bbox:
                                    logging.info(f"✅ Post centralizado: posição y={bbox['y']}, altura={bbox['height']}")
                                else:
                                    logging.warning("⚠️ Post pode não estar completamente visível")
                                    await asyncio.sleep(1)
                        except Exception as e:
                            logging.warning(f"⚠️ Erro ao centralizar post: {e}")
                            await asyncio.sleep(2)
                        
                        # PASSO 5: Processar o post
                        logging.info("🔄 PASSO 5: Processando post completo...")
                        success = await process_single_post(post_element, page, state)
                        
                        if success:
                            new_leads_found += 1
                            logging.info("🎉 SUCESSO COMPLETO! Post processado e comentado!")
                            logging.info("⏸️ Pausando 15 segundos antes do próximo (evitar rate limit)...")
                            await asyncio.sleep(15)
                        else:
                            logging.info("⚠️ Post processado mas sem comentário (filtrado ou já processado)")
                            logging.info("⏸️ Pausando 5 segundos antes do próximo...")
                            await asyncio.sleep(5)
                        
                        # PASSO 6: Avançar para próximo post
                        current_post_index += 1
                        logging.info(f"➡️ PASSO 6: Avançando para próximo post (#{current_post_index + 1})")
                            
                    except Exception as e:
                        logging.error(f"❌ Erro ao processar post #{current_post_index + 1}: {e}")
                        current_post_index += 1
                        await asyncio.sleep(3)
                        continue
                
                # Controle de ciclos vazios
                if posts_found_in_cycle == 0:
                    consecutive_empty_cycles += 1
                    logging.warning(f"⚠️ Ciclo vazio #{consecutive_empty_cycles}. Nenhum post novo encontrado.")
                    
                    if consecutive_empty_cycles >= 3:
                        logging.info("🔄 Muitos ciclos vazios. Resetando navegação...")
                        posts_processed_in_session = 0
                        consecutive_empty_cycles = 0
                        # Recarregar a página para buscar posts mais novos
                        await page.reload()
                        await asyncio.sleep(5)
                        
                        # Aguardar feed carregar novamente
                        try:
                            await page.wait_for_selector("div[role='feed']", timeout=10000)
                        except Exception:
                            pass
                else:
                    consecutive_empty_cycles = 0
                
                # Resumo do ciclo
                logging.info("📊" * 30)
                logging.info("📊 RESUMO DO CICLO COMPLETO")
                logging.info(f"📊 Posts encontrados neste ciclo: {posts_found_in_cycle}")
                logging.info(f"📊 Leads encontrados: {new_leads_found}")
                logging.info(f"📊 Total de posts processados na sessão: {posts_processed_in_session}")
                logging.info(f"📊 Ciclos vazios consecutivos: {consecutive_empty_cycles}")
                logging.info("📊" * 30)

                logging.info(f"🔄 Aguardando {LOOP_INTERVAL_SECONDS} segundos antes do próximo ciclo...")
                await asyncio.sleep(LOOP_INTERVAL_SECONDS)

            except KeyboardInterrupt:
                logging.info("🛑 Bot interrompido pelo usuário. Encerrando.")
                break
            except Exception:
                logging.exception("🚨 Ocorreu um erro inesperado no loop principal. Reiniciando em 30 segundos.")
                await asyncio.sleep(30)

    except Exception as e:
        logging.error(f"❌ Erro crítico no main_loop: {e}")
        logging.exception("Stack trace completo:")
        raise
    finally:
        # Fechar contexto Playwright
        try:
            if 'login_manager' in locals():
                await login_manager.__aexit__(None, None, None)
                logging.info("✅ Contexto Playwright encerrado.")
        except Exception as e:
            logging.error(f"❌ Erro ao fechar Playwright: {e}")
        logging.info("🏁 Fim da execução do main_loop.")

def main():
    """Wrapper síncrono para a função assíncrona main_loop"""
    asyncio.run(main_loop())

if __name__ == '__main__':
    main()
