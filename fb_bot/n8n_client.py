# fb_bot/n8n_client.py
import requests
import logging
import json

def healthcheck_n8n(webhook_url: str) -> bool:
    """Verifica se o webhook do n8n está ativo e respondendo."""
    if not webhook_url:
        logging.error("❌ N8N HEALTH CHECK: URL do webhook não configurada")
        return False
    
    try:
        logging.info(f"🔍 N8N HEALTH CHECK: Testando conexão com {webhook_url}")
        
        # Teste GET no webhook - n8n pode responder 404/405 mas conexão ok
        response = requests.get(webhook_url, timeout=15)
        
        logging.info(f"📊 N8N HEALTH CHECK: Status {response.status_code}")
        
        # Status codes aceitáveis para health check:
        # 200 = OK (webhook com GET habilitado)
        # 404 = Webhook existe mas sem GET (normal)
        # 405 = Method not allowed (webhook só aceita POST - normal)
        if response.status_code in [200, 404, 405]:
            logging.info("✅ Health check do n8n passou. O serviço está no ar.")
            return True
        elif response.status_code >= 500:
            logging.error(f"❌ N8N HEALTH CHECK: Erro interno do servidor: {response.status_code}")
            logging.error(f"📄 Resposta: {response.text[:200]}")
            return False
        else:
            logging.warning(f"⚠️ N8N HEALTH CHECK: Status inesperado {response.status_code}")
            logging.warning(f"📄 Resposta: {response.text[:200]}")
            return True  # Assumir que pode funcionar
            
    except requests.exceptions.ConnectTimeout:
        logging.error("❌ N8N HEALTH CHECK: Timeout - n8n não responde")
        logging.error("💡 SOLUÇÃO: Verifique se o n8n está rodando na porta correta")
        return False
    except requests.exceptions.ConnectionError as e:
        logging.error(f"❌ N8N HEALTH CHECK: Falha de conexão: {str(e)[:100]}")
        logging.error("💡 SOLUÇÃO: Confirme se n8n está ativo e URL está correta")
        return False
    except requests.RequestException as e:
        logging.error(f"❌ N8N HEALTH CHECK: Erro na requisição: {str(e)[:100]}")
        return False

def ask_n8n(webhook_url: str, post_details: dict) -> str:
    """Envia os detalhes do post para o n8n e retorna a resposta da IA."""
    try:
        # Log detalhado dos dados sendo enviados
        logging.info("=" * 80)
        logging.info("🚀 ENVIANDO DADOS PARA N8N")
        logging.info(f"📡 URL do webhook: {webhook_url}")
        logging.info(f"👤 Autor: '{post_details.get('author', 'Não identificado')}'")
        logging.info(f"📝 Prompt ({len(post_details.get('prompt', ''))} chars): {post_details.get('prompt', 'Sem texto')[:100]}...")
        logging.info(f"🖼️ Imagem: {'Sim' if post_details.get('image_url') else 'Não'}")
        if post_details.get('image_url'):
            logging.info(f"🔗 URL da imagem: {post_details.get('image_url')[:100]}...")
        
        # Log do payload JSON completo
        payload_preview = json.dumps(post_details, ensure_ascii=False, indent=2)[:800]
        logging.info(f"📦 Payload JSON completo:")
        logging.info(payload_preview)
        if len(json.dumps(post_details)) > 800:
            logging.info("... (payload truncado para visualização)")
        
        logging.info("⏳ Fazendo requisição POST para n8n...")
        
        # Fazer requisição com headers adequados
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Facebook-Bot/1.0'
        }
        
        response = requests.post(webhook_url, json=post_details, headers=headers, timeout=90)
        
        logging.info(f"📊 Status da resposta: {response.status_code}")
        logging.info(f"⏱️ Tempo de resposta: {response.elapsed.total_seconds():.2f}s")
        logging.info(f"📋 Headers da resposta: {dict(response.headers)}")
        
        # Log da resposta bruta antes de processar
        response_text = response.text
        logging.info(f"📄 Resposta bruta: {response_text[:500]}...")
        
        response.raise_for_status()
        
        # Tentar processar como JSON
        try:
            response_data = response.json()
            logging.info(f"📥 Resposta JSON processada:")
            logging.info(json.dumps(response_data, ensure_ascii=False, indent=2))
            
            reply = response_data.get("reply")
            if reply:
                logging.info(f"✅ SUCESSO: Campo 'reply' encontrado!")
                logging.info(f"💬 RESPOSTA DA IA: '{reply}'")
                logging.info("=" * 80)
                return reply
            else:
                logging.error("❌ ERRO: N8N respondeu mas SEM campo 'reply'")
                logging.error("🔍 Campos disponíveis na resposta:")
                for key in response_data.keys():
                    logging.error(f"   - {key}: {str(response_data[key])[:100]}...")
                logging.info("=" * 80)
                return None
                
        except json.JSONDecodeError as e:
            logging.error(f"❌ ERRO: Resposta do n8n não é JSON válido: {e}")
            logging.error(f"📄 Resposta completa: {response_text}")
            logging.info("=" * 80)
            return None
            
    except requests.exceptions.HTTPError as e:
        logging.error(f"❌ ERRO HTTP NA COMUNICAÇÃO COM N8N: {e}")
        logging.error(f"🔍 Tipo de erro: {type(e).__name__}")
        if hasattr(e, 'response') and e.response is not None:
            logging.error(f"📊 Status HTTP: {e.response.status_code}")
            logging.error(f"📄 Resposta do servidor: {e.response.text[:500]}")
            
            # Análise específica do erro 404
            if e.response.status_code == 404:
                logging.error("💡 SOLUÇÃO PARA 404:")
                logging.error("   1. Verifique se o workflow do n8n está ativo")
                logging.error("   2. Confirme se o webhook aceita requisições POST")
                logging.error("   3. Verifique se a URL do webhook está correta")
                
        logging.info("=" * 80)
        return None
        
    except requests.exceptions.Timeout:
        logging.error("❌ TIMEOUT: N8N demorou mais de 90s para responder")
        logging.error("💡 SOLUÇÃO: Verifique se o n8n/IA não está sobrecarregado")
        logging.info("=" * 80)
        return None
        
    except requests.exceptions.ConnectionError as e:
        logging.error(f"❌ ERRO DE CONEXÃO COM N8N: {e}")
        logging.error("💡 SOLUÇÃO: Verifique se o n8n está rodando e acessível")
        logging.info("=" * 80)
        return None
        
    except requests.RequestException as e:
        logging.error(f"❌ ERRO GERAL NA REQUISIÇÃO: {e}")
        logging.error(f"🔍 Tipo de erro: {type(e).__name__}")
        logging.info("=" * 80)
        return None