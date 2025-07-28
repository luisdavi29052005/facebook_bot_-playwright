
# fb_bot/login.py

import json
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import logging

# Diretório para sessão persistente
SESSION_DIR = "./sessions/facebook_profile"
FB_URL = "https://www.facebook.com/"
COOKIES_FILE = "./cookies.json"

class PlaywrightFBLogin:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        
        # Criar diretório de sessão se não existir
        session_path = Path(SESSION_DIR)
        session_path.mkdir(parents=True, exist_ok=True)
        
        logging.info(f"📁 Usando diretório de sessão persistente: {SESSION_DIR}")
        
        # Usar launch_persistent_context para manter sessão
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=self.headless,
            viewport={'width': 1528, 'height': 738},
            locale='pt-BR',
            timezone_id='America/Sao_Paulo',
             user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
            args=[
                '--start-maximized',
                '--disable-notifications',
                '--disable-infobars',
                '--disable-extensions',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--lang=pt-BR,pt',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--allow-running-insecure-content'
            ]
        )
        
        # Aguardar contexto carregar
        await asyncio.sleep(2)
        
        # Obter página existente ou criar nova
        pages = self.context.pages
        if pages:
            self.page = pages[0]
            logging.info("✅ Usando página existente do contexto persistente")
        else:
            self.page = await self.context.new_page()
            logging.info("📄 Criando nova página no contexto persistente")
        
        # Primeiro tentar login com cookies se existirem
        if await self._try_cookie_login():
            logging.info("🍪 Login automático com cookies bem-sucedido!")
            return self
        
        # Verificar se já está logado na sessão persistente
        if await self._check_login_status():
            logging.info("✅ Login automático via sessão persistente bem-sucedido!")
            logging.info("🎉 Sessão do Facebook mantida com sucesso!")
            return self
        
        # Se não estiver logado, fazer login manual
        logging.info("🔐 Primeira execução ou sessão expirada - fazendo login manual...")
        if await self._perform_manual_login():
            logging.info("✅ Login manual concluído e sessão salva permanentemente!")
            logging.info("🔄 Próximas execuções usarão esta sessão automaticamente")
            return self
        else:
            raise Exception("❌ Falha no login manual")

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Com persistent context, não fechamos o contexto para manter a sessão
        # Apenas fechamos o playwright
        if hasattr(self, 'playwright'):
            try:
                await self.playwright.stop()
                logging.info("✅ Playwright encerrado - sessão mantida no disco")
            except Exception as e:
                logging.error(f"⚠️ Erro ao fechar Playwright: {e}")

    def _load_cookies(self):
        """Carrega cookies do arquivo cookies.json"""
        try:
            if not Path(COOKIES_FILE).exists():
                logging.warning(f"📄 Arquivo de cookies não encontrado: {COOKIES_FILE}")
                return None
                
            with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
                cookies_data = json.load(f)
                
            # Verificar se é o formato correto (com 'all' ou 'essential')
            if isinstance(cookies_data, dict):
                if 'all' in cookies_data:
                    cookies = cookies_data['all']
                elif 'essential' in cookies_data:
                    cookies = cookies_data['essential']
                else:
                    cookies = cookies_data
            elif isinstance(cookies_data, list):
                cookies = cookies_data
            else:
                logging.error("❌ Formato de cookies inválido")
                return None
                
            logging.info(f"🍪 Carregados {len(cookies)} cookies do arquivo")
            return cookies
            
        except Exception as e:
            logging.error(f"❌ Erro ao carregar cookies: {e}")
            return None

    async def _try_cookie_login(self):
        """Tenta fazer login usando cookies salvos"""
        try:
            cookies = self._load_cookies()
            if not cookies:
                logging.info("🍪 Nenhum cookie disponível para login automático")
                return False
                
            logging.info("🍪 Tentando login automático com cookies...")
            
            # Ir para o Facebook primeiro
            await self.page.goto(FB_URL, wait_until='domcontentloaded')
            await asyncio.sleep(2)
            
            # Aplicar cookies
            await self.context.add_cookies(cookies)
            logging.info("🍪 Cookies aplicados com sucesso")
            
            # Navegar novamente para ativar os cookies
            await self.page.goto(FB_URL, wait_until='domcontentloaded')
            await asyncio.sleep(5)  # Aguardar carregamento completo
            
            # Verificar se o login foi bem-sucedido
            if await self._check_login_status():
                logging.info("✅ Login com cookies realizado com sucesso!")
                return True
            else:
                logging.warning("⚠️ Cookies não resultaram em login válido")
                return False
                
        except Exception as e:
            logging.error(f"❌ Erro no login com cookies: {e}")
            return False

    async def _check_login_status(self):
        """Verifica se o usuário está logado usando sessão persistente"""
        try:
            logging.info("🔍 Verificando status de login...")
            
            # Múltiplas verificações para confirmar login
            login_indicators = [
                "a[aria-label='Home'], a[aria-label='Início']",
                "div[role='banner'] a[href*='facebook.com']",
                "a[href*='facebook.com'][aria-label*='Home']",
                "div[data-pagelet='NavigationUnit']",
                "[data-testid='nav_search_button']",
                "div[role='navigation']",
                "[data-testid='left_nav_menu_list']"
            ]
            
            for indicator in login_indicators:
                try:
                    element = await self.page.wait_for_selector(indicator, timeout=8000)
                    if element:
                        logging.info(f"✅ Login verificado via elemento: {indicator}")
                        current_url = self.page.url
                        logging.info(f"📍 URL atual: {current_url}")
                        return True
                except:
                    continue
            
            # Verificação por URL (não deve estar em páginas de login)
            current_url = self.page.url
            logging.info(f"📍 URL atual para verificação: {current_url}")
            
            if 'facebook.com' in current_url and not any(page in current_url for page in ['login', 'recover', 'checkpoint']):
                logging.info("✅ Login verificado via URL (não está em página de login)")
                return True
                
            logging.warning("❌ Não foi possível verificar login - redirecionamento para login detectado")
            return False
            
        except Exception as e:
            logging.error(f"⚠️ Erro na verificação de login: {e}")
            return False

    async def _perform_manual_login(self):
        """Realiza login manual aguardando interação do usuário"""
        try:
            await self.page.goto(FB_URL)
            logging.warning("🔐 ATENÇÃO: Sessão expirada ou primeira execução!")
            logging.info("👆 Por favor, faça login manualmente no navegador que foi aberto.")
            logging.info("📱 Use suas credenciais normais do Facebook")
            logging.info("⏳ Aguardando login... (timeout: 20 minutos)")
            logging.info("💡 DICA: Após o login, sua sessão será salva permanentemente!")
            
            # Aguardar até 20 minutos pelo login (mais tempo para usuário)
            for i in range(1200):  # 1200 segundos = 20 minutos
                # Log de progresso a cada minuto
                if i % 60 == 0 and i > 0:
                    minutes_passed = i // 60
                    logging.info(f"⏳ {minutes_passed} minuto(s) aguardando... (máximo 20 min)")
                
                if await self._quick_login_check():
                    logging.info("✅ Login manual detectado com sucesso!")
                    logging.info("💾 Salvando sessão permanentemente...")
                    await asyncio.sleep(5)  # Aguardar estabilização da sessão
                    logging.info("🎉 Sessão salva! Próximas execuções serão automáticas!")
                    return True
                    
                await asyncio.sleep(1)
            
            logging.error("❌ Timeout no login manual (20 minutos)")
            return False
            
        except Exception as e:
            logging.error(f"❌ Erro no login manual: {e}")
            return False

    async def _quick_login_check(self):
        """Verificação rápida de login durante processo manual"""
        try:
            # Verificações mais rápidas para o processo de login
            quick_indicators = [
                "a[aria-label='Home']",
                "a[aria-label='Início']", 
                "[data-testid='nav_search_button']"
            ]
            
            for indicator in quick_indicators:
                try:
                    element = await self.page.wait_for_selector(indicator, timeout=2000)
                    if element:
                        return True
                except:
                    continue
                    
            # Verificação de URL rápida
            current_url = self.page.url
            if ('facebook.com' in current_url and 
                not any(page in current_url for page in ['login', 'recover', 'checkpoint'])):
                return True
                
            return False
        except:
            return False

    async def navigate_to_group(self, group_url: str):
        """Navega para um grupo específico"""
        logging.info(f"🌍 Navegando para o grupo: {group_url}")
        await self.page.goto(group_url, wait_until='domcontentloaded')
        
        # Aguardar feed carregar
        try:
            await self.page.wait_for_selector("div[role='feed']", timeout=25000)
            await asyncio.sleep(2)
            logging.info("✅ Grupo carregado com sucesso")
        except Exception as e:
            logging.warning(f"⚠️ Erro ao carregar grupo: {e}")

    def get_page(self) -> Page:
        """Retorna a página atual para uso em outras funções"""
        return self.page

async def fb_login(headless: bool = False):
    """Função principal de login que retorna uma instância configurada"""
    login_manager = PlaywrightFBLogin(headless=headless)
    try:
        await login_manager.__aenter__()
        return login_manager
    except Exception as e:
        logging.error(f"❌ Falha crítica no login: {e}")
        await login_manager.__aexit__(None, None, None)
        return None
