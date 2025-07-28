
import pytest
import json
import threading
import time
from pathlib import Path
from state_manager import StateManager

def test_state_manager_init_empty(tmp_path):
    """Testa inicialização com arquivo vazio."""
    state_file = tmp_path / "empty_state.json"
    
    manager = StateManager(str(state_file))
    
    assert manager.get_count() == 0
    assert not manager.has("test_id")

def test_state_manager_load_existing(temp_state_file):
    """Testa carregamento de estado existente."""
    manager = StateManager(temp_state_file)
    
    assert manager.get_count() == 2
    assert manager.has("permalink:https://facebook.com/post/123")
    assert manager.has("hash:abc123")

def test_state_manager_add_post(tmp_path):
    """Testa adição de novo post."""
    state_file = tmp_path / "add_test.json"
    manager = StateManager(str(state_file))
    
    # Adicionar post
    manager.add("permalink:https://facebook.com/post/456")
    
    assert manager.has("permalink:https://facebook.com/post/456")
    assert manager.get_count() == 1
    
    # Verificar que foi salvo no arquivo
    with open(state_file, 'r') as f:
        data = json.load(f)
    assert "permalink:https://facebook.com/post/456" in data

def test_state_manager_duplicate_add(tmp_path):
    """Testa que posts duplicados não são adicionados."""
    state_file = tmp_path / "dup_test.json"
    manager = StateManager(str(state_file))
    
    # Adicionar mesmo post duas vezes
    manager.add("permalink:https://facebook.com/post/123")
    initial_count = manager.get_count()
    
    manager.add("permalink:https://facebook.com/post/123")
    
    assert manager.get_count() == initial_count

def test_state_manager_remove_post(temp_state_file):
    """Testa remoção de post."""
    manager = StateManager(temp_state_file)
    
    # Remover post existente
    result = manager.remove("hash:abc123")
    
    assert result is True
    assert not manager.has("hash:abc123")
    assert manager.get_count() == 1

def test_state_manager_remove_nonexistent(temp_state_file):
    """Testa remoção de post que não existe."""
    manager = StateManager(temp_state_file)
    
    result = manager.remove("nonexistent_id")
    
    assert result is False
    assert manager.get_count() == 2  # Nada mudou

def test_state_manager_clear(temp_state_file):
    """Testa limpeza completa do estado."""
    manager = StateManager(temp_state_file)
    
    assert manager.get_count() > 0
    
    manager.clear()
    
    assert manager.get_count() == 0
    assert not manager.has("permalink:https://facebook.com/post/123")

def test_state_manager_normalize_ids(tmp_path):
    """Testa normalização de IDs."""
    state_file = tmp_path / "normalize_test.json"
    
    # Criar arquivo com IDs antigos
    old_data = [
        "https://facebook.com/post/123?param=value",  # URL com parâmetros
        "permalink:https://facebook.com/post/456#anchor",  # Com âncora
        "hash:abc123"  # Já normalizado
    ]
    
    with open(state_file, 'w') as f:
        json.dump(old_data, f)
    
    manager = StateManager(str(state_file))
    
    # Verificar que IDs foram normalizados
    assert manager.has("permalink:https://facebook.com/post/123")
    assert manager.has("permalink:https://facebook.com/post/456")
    assert manager.has("hash:abc123")

def test_state_manager_thread_safety(tmp_path):
    """Testa segurança de thread com writes simultâneos."""
    state_file = tmp_path / "thread_test.json"
    manager = StateManager(str(state_file))
    
    def add_posts(start_num, count):
        for i in range(start_num, start_num + count):
            manager.add(f"permalink:https://facebook.com/post/{i}")
            time.sleep(0.001)  # Pequena pausa para simular concorrência
    
    # Criar threads que adicionam posts simultaneamente
    thread1 = threading.Thread(target=add_posts, args=(1, 50))
    thread2 = threading.Thread(target=add_posts, args=(100, 50))
    
    thread1.start()
    thread2.start()
    
    thread1.join()
    thread2.join()
    
    # Verificar que todos os posts foram adicionados
    assert manager.get_count() == 100
    
    # Verificar integridade do arquivo
    with open(state_file, 'r') as f:
        data = json.load(f)
    assert len(data) == 100

def test_state_manager_force_save(tmp_path):
    """Testa salvamento forçado."""
    state_file = tmp_path / "force_save_test.json"
    manager = StateManager(str(state_file))
    
    # Adicionar post e forçar save
    manager._processed_ids.add("test_post")  # Adicionar diretamente sem save automático
    
    # Verificar que não foi salvo ainda
    assert not state_file.exists() or len(json.load(open(state_file))) == 0
    
    # Forçar save
    manager.force_save()
    
    # Verificar que foi salvo
    with open(state_file, 'r') as f:
        data = json.load(f)
    assert "test_post" in data
