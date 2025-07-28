
from flask import Flask, render_template, jsonify, request
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
import tempfile

# Importar módulos do bot
from main import main_loop, stop_event
from logger import setup_logging, bot_logger
from state_manager import StateManager
from fb_bot.config import BotConfig

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

# Cache de configuração e status
_config_cache = None
_config_cache_time = 0
_n8n_status_cache = {'healthy': False, 'last_check': 0}

# Lock para config saving
config_lock = threading.Lock()

def get_config(force_reload=False):
    """Obtém configurações com cache."""
    global _config_cache, _config_cache_time

    current_time = time.time()
    if force_reload or not _config_cache or (current_time - _config_cache_time) > 60:
        # Recarregar apenas se necessário
        from dotenv import load_dotenv
        load_dotenv(override=True)

        if 'fb_bot.config' in sys.modules:
            importlib.reload(sys.modules['fb_bot.config'])

        from fb_bot.config import BotConfig
        _config_cache = BotConfig.load_from_env()
        _config_cache_time = current_time

    return _config_cache

def read_recent_logs(lines=30):
    """Lê logs recentes, filtrando ruído."""
    try:
        log_file = Path('logs/bot.log')
        if not log_file.exists():
            return ["Nenhum log disponível"]

        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()

        # Filtrar logs irrelevantes
        filtered_lines = []
        skip_patterns = [
            'GET /api/status',
            'GET /',
            'werkzeug',
            'Sistema de logging configurado'
        ]

        for line in all_lines:
            line_clean = line.strip()
            if not any(pattern in line_clean for pattern in skip_patterns):
                filtered_lines.append(line_clean)

        return filtered_lines[-lines:] if len(filtered_lines) > lines else filtered_lines
    except Exception as e:
        return [f"Erro ao ler logs: {str(e)}"]

async def check_n8n_health_async(config):
    """Verifica saúde do n8n de forma assíncrona."""
    try:
        from fb_bot.n8n_client import healthcheck_n8n
        return await healthcheck_n8n(config.n8n_webhook_url)
    except Exception:
        return False

def check_n8n_health(config):
    """Verifica saúde do n8n com cache otimizado."""
    global _n8n_status_cache

    current_time = time.time()
    cache_duration = 300  # 5 minutos

    if (current_time - _n8n_status_cache['last_check']) < cache_duration:
        return _n8n_status_cache['healthy']

    try:
        # Run async check in thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _n8n_status_cache['healthy'] = loop.run_until_complete(check_n8n_health_async(config))
        _n8n_status_cache['last_check'] = current_time
        loop.close()
    except Exception:
        _n8n_status_cache['healthy'] = False

    return _n8n_status_cache['healthy']

@app.route('/')
def dashboard():
    """Dashboard principal."""
    config = get_config()
    return render_template('dashboard.html', 
                         bot_running=bot_running,
                         bot_stats=bot_stats,
                         config={
                             'webhook_url': config.n8n_webhook_url or 'Não configurado',
                             'group_url': config.facebook_group_url or 'Não configurado',
                             'headless': config.headless,
                             'interval': config.loop_interval_seconds,
                             'keywords': config.keywords
                         })

@app.route('/logs')
def logs():
    """Página de logs."""
    return render_template('logs.html', logs=read_recent_logs(50))

@app.route('/config')
def config_page():
    """Página de configurações."""
    config = get_config()
    return render_template('config.html', config={
        'webhook_url': config.n8n_webhook_url,
        'group_url': config.facebook_group_url,
        'keywords': config.keywords,
        'interval': config.loop_interval_seconds,
        'headless': config.headless
    })

@app.route('/api/status')
def api_status():
    """API de status otimizada."""
    config = get_config()

    try:
        state = StateManager()
        processed_count = len(state._processed_ids) if hasattr(state, '_processed_ids') else 0
    except:
        processed_count = 0

    return jsonify({
        'bot_running': bot_running,
        'n8n_healthy': check_n8n_health(config) if config.n8n_webhook_url else False,
        'processed_posts': processed_count,
        'stats': bot_stats,
        'logs': read_recent_logs(5),
        'config_valid': config.is_valid()[0]
    })

@app.route('/api/save-config', methods=['POST'])
def save_config():
    """Salvar configurações com escrita atômica."""
    try:
        data = request.get_json()

        webhook_url = data.get('webhook_url', '').strip()
        group_url = data.get('group_url', '').strip()
        keywords_str = data.get('keywords', '').strip()
        interval = int(data.get('interval', 60))
        headless = bool(data.get('headless', True))

        # Processar palavras-chave
        keywords = [k.strip() for k in keywords_str.split(',') if k.strip()] if keywords_str else []

        # Validações
        if not webhook_url:
            return jsonify({'success': False, 'message': 'URL do webhook é obrigatória'})
        if not group_url:
            return jsonify({'success': False, 'message': 'URL do grupo é obrigatória'})
        if interval < 30:
            return jsonify({'success': False, 'message': 'Intervalo mínimo é 30 segundos'})
        if interval > 3600:
            return jsonify({'success': False, 'message': 'Intervalo máximo é 3600 segundos'})

        # Salvar no .env com escrita atômica
        with config_lock:
            env_vars = {
                'N8N_WEBHOOK_URL': webhook_url,
                'FACEBOOK_GROUP_URL': group_url,
                'KEYWORDS': json.dumps(keywords),
                'LOOP_INTERVAL_SECONDS': str(interval),
                'HEADLESS': str(headless).lower()
            }

            # Ler .env existente
            env_content = {}
            if os.path.exists('.env'):
                with open('.env', 'r') as f:
                    for line in f:
                        if '=' in line and not line.startswith('#'):
                            key, value = line.strip().split('=', 1)
                            env_content[key] = value

            # Atualizar
            env_content.update(env_vars)

            # Escrever atomicamente usando arquivo temporário
            with tempfile.NamedTemporaryFile(mode='w', delete=False, dir='.', suffix='.env.tmp') as tmp_file:
                for key, value in env_content.items():
                    tmp_file.write(f'{key}={value}\n')
                tmp_file.flush()
                
                # Renomear para .env (operação atômica)
                os.replace(tmp_file.name, '.env')

            # Invalidar cache e recarregar config
            global _config_cache
            _config_cache = None
            new_config = get_config(force_reload=True)
            
            # Recarregar módulo de config
            if 'fb_bot.config' in sys.modules:
                importlib.reload(sys.modules['fb_bot.config'])

        bot_logger.info(f"Configurações atualizadas: {len(keywords)} palavras-chave, intervalo {interval}s")

        return jsonify({
            'success': True, 
            'message': 'Configurações salvas com sucesso!'
        })

    except Exception as e:
        bot_logger.error(f"Erro ao salvar configurações: {e}")
        return jsonify({'success': False, 'message': f'Erro: {str(e)}'})

@app.route('/api/start', methods=['POST'])
def start_bot():
    """Iniciar bot com verificação de thread existente."""
    global bot_thread, bot_running

    # Verificar se já está rodando
    if bot_thread and bot_thread.is_alive():
        return jsonify({'success': False, 'message': 'Bot já está rodando'})

    config = get_config(force_reload=True)
    is_valid, error_msg = config.is_valid()

    if not is_valid:
        return jsonify({'success': False, 'message': f'Configuração inválida: {error_msg}'})

    if not check_n8n_health(config):
        return jsonify({'success': False, 'message': 'n8n não está acessível'})

    # Limpar stop event
    stop_event.clear()

    # Iniciar bot
    bot_thread = threading.Thread(target=run_bot_wrapper, daemon=True)
    bot_thread.start()

    time.sleep(1)  # Aguardar inicialização

    if bot_running:
        bot_stats['start_time'] = datetime.now().isoformat()
        return jsonify({'success': True, 'message': 'Bot iniciado com sucesso'})
    else:
        return jsonify({'success': False, 'message': 'Falha ao iniciar bot'})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    """Parar bot com join e timeout."""
    global bot_running, bot_thread

    # Setar stop event
    stop_event.set()
    bot_running = False
    bot_stats['start_time'] = None
    
    # Fazer join com timeout se thread existe
    if bot_thread and bot_thread.is_alive():
        bot_thread.join(timeout=30)
        if bot_thread.is_alive():
            bot_logger.warning("Thread do bot não finalizou no timeout")
            return jsonify({
                'success': True, 
                'message': 'Bot parado (timeout na finalização)',
                'status': 'warning'
            })

    bot_logger.info("Bot parado pelo usuário")
    return jsonify({'success': True, 'message': 'Bot parado'})

@app.route('/api/test-webhook', methods=['POST'])
def test_webhook():
    """Testar webhook."""
    try:
        data = request.get_json()
        webhook_url = data.get('webhook_url', '').strip()

        if not webhook_url:
            return jsonify({'success': False, 'message': 'URL obrigatória'})

        # Run async test in thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            from fb_bot.n8n_client import healthcheck_n8n
            result = loop.run_until_complete(healthcheck_n8n(webhook_url))
            
            if result:
                return jsonify({'success': True, 'message': 'Webhook funcionando'})
            else:
                return jsonify({'success': False, 'message': 'Webhook não acessível'})
        finally:
            loop.close()
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro: {str(e)}'})

def run_bot_wrapper():
    """Wrapper para executar bot."""
    global bot_running

    try:
        bot_running = True
        bot_logger.info("Bot iniciado")
        asyncio.run(main_loop())
    except Exception as e:
        bot_logger.error(f"Erro no bot: {e}")
    finally:
        bot_running = False
        bot_logger.info("Bot parado")

if __name__ == '__main__':
    setup_logging()
    app.run(host='0.0.0.0', port=5000, debug=False)
