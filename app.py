
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
import json
import os
import threading
import time
from pathlib import Path
import logging
from datetime import datetime
import importlib
import sys
import asyncio

# Importar módulos do bot
from main import main_loop
from logger import setup_logging
from state_manager import StateManager

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Estado global do bot
bot_thread = None
bot_running = False
bot_stats = {
    'posts_processed': 0,
    'comments_sent': 0,
    'last_activity': None,
    'start_time': None
}

# Cache do status do n8n para evitar muitas verificações
n8n_status_cache = {
    'healthy': False,
    'last_check': 0,
    'check_interval': 300  # 5 minutos
}

def reload_config():
    """Recarrega as configurações após mudanças"""
    try:
        # Recarregar variáveis de ambiente do arquivo .env
        from dotenv import load_dotenv
        load_dotenv(override=True)
        
        # Recarregar módulo de configuração
        if 'fb_bot.config' in sys.modules:
            importlib.reload(sys.modules['fb_bot.config'])
        
        # Importar configurações atualizadas
        from fb_bot.config import N8N_WEBHOOK_URL, FB_GROUP_URL, HEADLESS, LOOP_INTERVAL_SECONDS, KEYWORDS
        return N8N_WEBHOOK_URL, FB_GROUP_URL, HEADLESS, LOOP_INTERVAL_SECONDS, KEYWORDS
    except Exception as e:
        logging.error(f"Erro ao recarregar configurações: {e}")
        return None, None, True, 60, []

def get_current_config():
    """Obtém as configurações atuais (recarregadas)"""
    N8N_WEBHOOK_URL, FB_GROUP_URL, HEADLESS, LOOP_INTERVAL_SECONDS, KEYWORDS = reload_config()
    
    keywords_list = KEYWORDS if isinstance(KEYWORDS, list) else []
    return {
        'webhook_url': N8N_WEBHOOK_URL or '',
        'group_url': FB_GROUP_URL or '',
        'keywords': keywords_list,
        'interval': LOOP_INTERVAL_SECONDS,
        'headless': HEADLESS
    }

def read_log_file(lines=50):
    """Lê as últimas linhas do arquivo de log, filtrando logs HTTP desnecessários"""
    try:
        with open('bot_activity.log', 'r', encoding='utf-8') as f:
            log_lines = f.readlines()
            
            # Filtrar logs HTTP da interface
            filtered_lines = []
            for line in log_lines:
                line_text = line.strip()
                # Pular logs de requisições HTTP da interface
                if 'GET /api/status' in line_text:
                    continue
                if 'GET /' in line_text and 'HTTP/1.1' in line_text:
                    continue
                if 'POST /api/' in line_text and 'HTTP/1.1' in line_text:
                    continue
                # Pular logs do werkzeug
                if '[werkzeug]' in line_text:
                    continue
                
                filtered_lines.append(line_text)
            
            # Retornar as últimas N linhas filtradas
            return filtered_lines[-lines:] if len(filtered_lines) > lines else filtered_lines
    except FileNotFoundError:
        return ["Arquivo de log não encontrado"]
    except Exception as e:
        return [f"Erro ao ler logs: {str(e)}"]

def get_processed_posts():
    """Obtém informações dos posts processados"""
    try:
        state = StateManager()
        return len(state._processed_ids) if hasattr(state, '_processed_ids') else 0
    except:
        return 0

def check_n8n_health_cached(webhook_url):
    """Verifica saúde do n8n com cache para evitar logs excessivos"""
    import time
    
    current_time = time.time()
    
    # Se já verificou recentemente, retorna o status em cache
    if (current_time - n8n_status_cache['last_check']) < n8n_status_cache['check_interval']:
        return n8n_status_cache['healthy']
    
    # Faz nova verificação
    from fb_bot.n8n_client import healthcheck_n8n
    try:
        n8n_status_cache['healthy'] = healthcheck_n8n(webhook_url)
        n8n_status_cache['last_check'] = current_time
        
        # Log apenas quando o status muda ou na primeira verificação
        if n8n_status_cache['last_check'] == current_time:
            if n8n_status_cache['healthy']:
                logging.info("✅ n8n health check inicial: Serviço está operacional")
            else:
                logging.warning("⚠️ n8n health check inicial: Serviço não está acessível")
                
    except Exception as e:
        logging.error(f"❌ Erro no health check do n8n: {e}")
        n8n_status_cache['healthy'] = False
    
    return n8n_status_cache['healthy']

def save_env_config(webhook_url, group_url, keywords, interval, headless):
    """Salva as configurações no arquivo .env"""
    env_path = '.env'
    env_vars = {}
    
    # Ler arquivo .env existente
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key] = value
    
    # Atualizar variáveis
    env_vars['N8N_WEBHOOK_URL'] = webhook_url
    env_vars['FACEBOOK_GROUP_URL'] = group_url
    env_vars['KEYWORDS'] = json.dumps(keywords) if isinstance(keywords, list) else str(keywords)
    env_vars['LOOP_INTERVAL_SECONDS'] = str(interval)
    env_vars['HEADLESS'] = str(headless).lower()
    
    # Escrever arquivo .env
    with open(env_path, 'w', encoding='utf-8') as f:
        for key, value in env_vars.items():
            f.write(f'{key}={value}\n')
    
    # Atualizar variáveis de ambiente do processo atual
    os.environ['N8N_WEBHOOK_URL'] = webhook_url
    os.environ['FACEBOOK_GROUP_URL'] = group_url
    os.environ['KEYWORDS'] = json.dumps(keywords) if isinstance(keywords, list) else str(keywords)
    os.environ['LOOP_INTERVAL_SECONDS'] = str(interval)
    os.environ['HEADLESS'] = str(headless).lower()

@app.route('/')
def dashboard():
    """Página principal do dashboard"""
    config = get_current_config()
    return render_template('dashboard.html', 
                         bot_running=bot_running,
                         bot_stats=bot_stats,
                         config={
                             'webhook_url': config['webhook_url'] or 'Não configurado',
                             'group_url': config['group_url'] or 'Não configurado',
                             'headless': config['headless'],
                             'interval': config['interval'],
                             'keywords': config['keywords'] or []
                         })

@app.route('/logs')
def logs():
    """Página de visualização de logs"""
    log_lines = read_log_file(100)
    return render_template('logs.html', logs=log_lines)

@app.route('/config')
def config():
    """Página de configurações"""
    current_config = get_current_config()
    return render_template('config.html', config=current_config)

@app.route('/api/save-config', methods=['POST'])
def save_config():
    """Salvar configurações"""
    try:
        data = request.get_json()
        
        webhook_url = data.get('webhook_url', '').strip()
        group_url = data.get('group_url', '').strip()
        keywords_str = data.get('keywords', '').strip()
        interval = int(data.get('interval', 60))
        headless = data.get('headless', True)
        
        # Converter string para boolean se necessário
        if isinstance(headless, str):
            headless = headless.lower() in ('true', '1', 't', 'yes')
        
        # Processar palavras-chave
        if keywords_str:
            keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
        else:
            keywords = []
        
        # Validações básicas
        if not webhook_url:
            return jsonify({'success': False, 'message': 'URL do webhook é obrigatória'})
        
        if not group_url:
            return jsonify({'success': False, 'message': 'URL do grupo Facebook é obrigatória'})
        
        if interval < 30:
            return jsonify({'success': False, 'message': 'Intervalo mínimo é 30 segundos'})
        
        # Salvar configurações
        save_env_config(webhook_url, group_url, keywords, interval, headless)
        
        # Recarregar configurações
        reload_config()
        
        # Log da ação
        logging.info(f"Configurações atualizadas: webhook={webhook_url[:20]}..., interval={interval}s, headless={headless}, keywords={len(keywords)}")
        
        return jsonify({
            'success': True, 
            'message': 'Configurações salvas e aplicadas com sucesso!',
            'config': get_current_config()  # Retornar configuração atualizada
        })
        
    except Exception as e:
        logging.error(f"Erro ao salvar configurações: {e}")
        return jsonify({'success': False, 'message': f'Erro ao salvar configurações: {str(e)}'})

@app.route('/api/status')
def api_status():
    """API para obter status do bot"""
    try:
        config = get_current_config()
        
        n8n_status = False
        if config['webhook_url']:
            try:
                n8n_status = check_n8n_health_cached(config['webhook_url'])
            except Exception as e:
                logging.error(f"Erro no health check: {e}")
        
        logs = read_log_file(10)
        
        return jsonify({
            'bot_running': bot_running,
            'n8n_healthy': n8n_status,
            'processed_posts': get_processed_posts(),
            'stats': bot_stats,
            'logs': logs if logs else ["Nenhum log disponível"],
            'config': config
        })
    except Exception as e:
        logging.error(f"Erro na API status: {e}")
        return jsonify({
            'bot_running': False,
            'n8n_healthy': False,
            'processed_posts': 0,
            'stats': bot_stats,
            'logs': [f"Erro ao obter status: {str(e)}"],
            'config': get_current_config()
        })

@app.route('/api/start', methods=['POST'])
def start_bot():
    """Iniciar o bot"""
    global bot_thread, bot_running, bot_stats

    if bot_running:
        return jsonify({'success': False, 'message': 'Bot já está rodando'})

    try:
        config = get_current_config()
        
        # Verificar configurações
        if not config['webhook_url']:
            return jsonify({'success': False, 'message': 'URL do webhook n8n não configurada. Acesse as Configurações.'})

        if not config['group_url']:
            return jsonify({'success': False, 'message': 'URL do grupo Facebook não configurada. Acesse as Configurações.'})

        # Verificar se n8n está disponível
        try:
            if not check_n8n_health_cached(config['webhook_url']):
                return jsonify({'success': False, 'message': 'n8n não está acessível. Verifique se o serviço está rodando e a URL está correta.'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Erro ao conectar com n8n: {str(e)}'})

        # Iniciar bot
        bot_thread = threading.Thread(target=run_bot_wrapper)
        bot_thread.daemon = True
        bot_thread.start()

        # Aguardar um pouco para verificar se o bot iniciou
        time.sleep(2)

        if bot_running:
            bot_stats['start_time'] = datetime.now().isoformat()
            return jsonify({'success': True, 'message': 'Bot iniciado com sucesso'})
        else:
            return jsonify({'success': False, 'message': 'Falha ao iniciar o bot. Verifique os logs para mais detalhes.'})

    except Exception as e:
        logging.error(f"Erro ao iniciar bot: {e}")
        return jsonify({'success': False, 'message': f'Erro ao iniciar bot: {str(e)}'})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    """Parar o bot"""
    global bot_running, bot_stats
    
    try:
        bot_running = False
        bot_stats['start_time'] = None
        logging.info("Bot parado pelo usuário")
        return jsonify({'success': True, 'message': 'Bot parado com sucesso'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao parar bot: {str(e)}'})

@app.route('/api/test-webhook', methods=['POST'])
def test_webhook():
    """Testar conectividade do webhook"""
    try:
        data = request.get_json()
        webhook_url = data.get('webhook_url', '').strip()
        
        if not webhook_url:
            return jsonify({'success': False, 'message': 'URL do webhook é obrigatória'})
        
        from fb_bot.n8n_client import healthcheck_n8n
        
        # Testar conexão (sempre faz verificação real para teste)
        is_healthy = healthcheck_n8n(webhook_url)
        
        if is_healthy:
            return jsonify({'success': True, 'message': 'Webhook está acessível e funcionando'})
        else:
            return jsonify({'success': False, 'message': 'Webhook não está acessível ou não está respondendo corretamente'})
            
    except Exception as e:
        logging.error(f"Erro ao testar webhook: {e}")
        return jsonify({'success': False, 'message': f'Erro ao testar webhook: {str(e)}'})

def run_bot_wrapper():
    """Wrapper para executar o bot em thread separada"""
    global bot_running, bot_stats

    try:
        setup_logging()
        bot_running = True
        logging.info("Bot iniciado com sucesso")

        config = get_current_config()
        from fb_bot.n8n_client import healthcheck_n8n
        
        # Verificar n8n antes de iniciar
        if not healthcheck_n8n(config['webhook_url']):
            raise Exception("n8n não está acessível")

        # Executar loop principal do bot de forma assíncrona
        asyncio.run(main_loop())
    except Exception as e:
        logging.error(f"Erro no bot: {e}")
        bot_running = False
    finally:
        bot_running = False
        logging.info("Bot parado")

if __name__ == '__main__':
    setup_logging()
    app.run(host='0.0.0.0', port=5000, debug=True)
