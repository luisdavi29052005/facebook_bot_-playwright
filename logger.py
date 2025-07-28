
import logging
import sys
from logging.handlers import RotatingFileHandler
import os

def setup_logging(level=logging.INFO):
    """Configura sistema de logging limpo e eficiente."""
    
    # Criar diretório de logs se não existir
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Formatter mais limpo
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-5s] %(message)s",
        datefmt="%H:%M:%S"
    )
    
    # Handler para arquivo principal
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "bot.log"),
        maxBytes=2*1024*1024,  # 2MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    
    # Handler para console (apenas INFO e acima)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # Handler para erros críticos
    error_handler = RotatingFileHandler(
        os.path.join(log_dir, "errors.log"),
        maxBytes=1*1024*1024,  # 1MB
        backupCount=2,
        encoding='utf-8'
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    
    # Configurar logger principal
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Limpar handlers existentes
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Adicionar novos handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(error_handler)
    
    # Silenciar loggers de bibliotecas externas
    logging.getLogger('selenium').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('playwright').setLevel(logging.WARNING)
    
    logging.info("Sistema de logging configurado")

class BotLogger:
    """Logger específico para operações do bot com controle de verbosidade."""
    
    def __init__(self):
        self.logger = logging.getLogger('bot')
        self._last_message = ""
        self._message_count = 0
    
    def info(self, message, force=False):
        """Log info com controle de repetição."""
        if message != self._last_message or force:
            self.logger.info(message)
            self._last_message = message
            self._message_count = 1
        else:
            self._message_count += 1
            if self._message_count % 10 == 0:  # Log a cada 10 repetições
                self.logger.info(f"{message} (repetido {self._message_count}x)")
    
    def success(self, message):
        """Log de sucesso."""
        self.logger.info(f"✅ {message}")
    
    def error(self, message):
        """Log de erro."""
        self.logger.error(f"❌ {message}")
    
    def warning(self, message):
        """Log de aviso."""
        self.logger.warning(f"⚠️ {message}")
    
    def debug(self, message):
        """Log de debug."""
        self.logger.debug(message)

# Instância global do logger do bot
bot_logger = BotLogger()
