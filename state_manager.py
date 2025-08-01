import json
import threading
from pathlib import Path
from typing import Set, List
import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class StateManager:
    """Gerenciador de estado thread-safe para posts processados."""

    def __init__(self, state_file: str = "processed_posts_state.json"):
        self.state_file = Path(state_file)
        self._processed_ids: Set[str] = set()
        self._lock = threading.Lock()
        self._load_state()

    def _load_state(self):
        """Carrega estado do arquivo com normalização de IDs."""
        try:
            if self.state_file.exists() and self.state_file.stat().st_size > 0:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        logger.debug("Arquivo de estado vazio, inicializando com conjunto vazio")
                        return set()

                    data = json.loads(content)
                    if isinstance(data, list):
                        return set(data)
                    elif isinstance(data, dict):
                        return set(data.get('processed_posts', []))
            return set()
        except json.JSONDecodeError as e:
            logger.warning(f"Arquivo de estado corrompido, reinicializando: {e}")
            # Remove arquivo corrompido e reinicializa
            try:
                self.state_file.unlink()
            except Exception:
                pass
            return set()
        except Exception as e:
            logger.error(f"Erro ao carregar estado: {e}")
            return set()

    def _normalize_post_id(self, post_id: str) -> str:
        """Normaliza ID do post para formato consistente."""
        if not post_id:
            return post_id

        # Se já é um permalink, limpar e retornar
        if post_id.startswith("permalink:"):
            url = post_id[10:]  # Remove "permalink:"
            return f"permalink:{self._clean_url(url)}"

        # Se é URL direta, converter para permalink
        if post_id.startswith(("http://", "https://")):
            return f"permalink:{self._clean_url(post_id)}"

        # Outros formatos mantém como estão
        return post_id

    def _clean_url(self, url: str) -> str:
        """Limpa URL removendo parâmetros desnecessários."""
        try:
            # Remove query parameters e fragments
            clean_url = url.split("?")[0].split("#")[0]

            # Garantir que é URL válida
            parsed = urlparse(clean_url)
            if parsed.scheme and parsed.netloc:
                return clean_url

        except Exception:
            pass

        return url

    def _save_state(self):
        """Salva estado no arquivo."""
        try:
            # Garantir que diretório existe
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            # Converter set para lista para JSON
            data = list(self._processed_ids)

            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug(f"Estado salvo: {len(data)} posts")

        except Exception as e:
            logger.error(f"Erro ao salvar estado: {e}")

    def has(self, post_id: str) -> bool:
        """Verifica se post já foi processado."""
        normalized_id = self._normalize_post_id(post_id)
        with self._lock:
            return normalized_id in self._processed_ids

    def add(self, post_id: str):
        """Adiciona post ao estado processado."""
        normalized_id = self._normalize_post_id(post_id)
        with self._lock:
            if normalized_id not in self._processed_ids:
                self._processed_ids.add(normalized_id)
                self._save_state()
                logger.debug(f"Post adicionado ao estado: {normalized_id}")

    def remove(self, post_id: str) -> bool:
        """Remove post do estado processado."""
        normalized_id = self._normalize_post_id(post_id)
        with self._lock:
            if normalized_id in self._processed_ids:
                self._processed_ids.remove(normalized_id)
                self._save_state()
                logger.debug(f"Post removido do estado: {normalized_id}")
                return True
            return False

    def clear(self):
        """Limpa todo o estado."""
        with self._lock:
            self._processed_ids.clear()
            self._save_state()
            logger.info("Estado limpo")

    def force_save(self):
        """Força salvamento do estado."""
        with self._lock:
            self._save_state()
            logger.info("Estado salvo forçadamente")

    def get_count(self) -> int:
        """Retorna número de posts processados."""
        with self._lock:
            return len(self._processed_ids)

    def get_recent(self, limit: int = 10) -> List[str]:
        """Retorna posts processados recentes."""
        with self._lock:
            # Como set não tem ordem, retornar amostra
            posts = list(self._processed_ids)
            return posts[-limit:] if len(posts) > limit else posts