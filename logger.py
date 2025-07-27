# logger.py
import logging
import sys
from logging.handlers import RotatingFileHandler
import os

def setup_logging():
    """Configura sistema de logging aprimorado com rotação de arquivos."""
    
    # Criar diretório de logs se não existir
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Configurar formatador mais detalhado
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Handler para arquivo com rotação (máximo 5MB, manter 5 backups)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "bot_activity.log"),
        maxBytes=5*1024*1024,  # 5MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # Handler para console com formatação mais limpa
    console_formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-5s] %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO)
    
    # Handler separado para erros críticos
    error_handler = RotatingFileHandler(
        os.path.join(log_dir, "bot_errors.log"),
        maxBytes=2*1024*1024,  # 2MB
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    
    # Configurar logger principal
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Limpar handlers existentes
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Adicionar novos handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(error_handler)
    
    # Configurar loggers específicos para bibliotecas externas
    logging.getLogger('selenium').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    
    logging.info("✅ Sistema de logging configurado com sucesso")