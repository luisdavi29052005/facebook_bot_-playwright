import json
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import logging

# Diretório para sessão persistente
SESSION_DIR = "./sessions/facebook_profile"
FB_URL = "https://web.facebook.com/?_rdc=1&_rdr"
COOKIES_FILE = "./cookies.json"
STORAGE_STATE_FILE = "./sessions/storage_state.json"

class PlaywrightFBLogin:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None
        self.playwright = None

    async def __aenter__(self):
        self.playwright = await async_playwright().start()

        # Criar diretório de sessão se não existir
        session_path = Path(SESSION_DIR)
        session_path.mkdir(parents=True, exist_ok=True)

        logging.info(f"📁 Usando diretório de sessão persistente: {SESSION_DIR}")

        # Configuração robusta do contexto
        context_options = {
            'user_data_dir': SESSION_DIR,
            'headless': self.headless,
            'viewport': {'width': 1366, 'height': 768},
            'locale': 'pt-BR',
            'timezone_id': 'America/Sao_Paulo',
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'extra_http_headers': {
                'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br'
            },
            'args': [
                '--disable-notifications',
                '--disable-infobars',
                '--disable-extensions',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--allow-running-insecure-content',
                '--disable-features=VizDisplayCompositor'
            ]
        }

        # Para launch_persistent_context, o storage_state é carregado automaticamente
        # através do user_data_dir, então não precisamos especificar separadamente
        storage_state_path = Path(STORAGE_STATE_FILE)
        if storage_state_path.exists():
            logging.info("🗂️ Storage state será carregado automaticamente via user_data_dir")

        self.context = await self.playwright.chromium.launch_persistent_context(**context_options)

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

        # Configurar interceptadores de requisição para melhor performance
        await self.page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", lambda route: route.abort())

        # Garantir login válido
        if await self.ensure_logged_in():
            return self
        else:
            raise Exception("❌ Falha no processo de login")

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, 'playwright') and self.playwright:
            try:
                # Salvar storage state antes de fechar
                if self.context:
                    await self._save_storage_state()
                await self.playwright.stop()
                logging.info("✅ Playwright encerrado - sessão mantida")
            except Exception as e:
                logging.error(f"⚠️ Erro ao fechar Playwright: {e}")

    async def ensure_logged_in(self):
        """Garante que o usuário está logado com múltiplas estratégias."""
        try:
            logging.info("🔍 Verificando status de login...")

            # Navegar para Facebook com retry
            if not await self._navigate_to_facebook():
                return False

            # Verificar se já está logado via URL primeiro (mais rápido)
            current_url = self.page.url.lower()
            if ('/home.php' in current_url or 
                '/groups/' in current_url or 
                (current_url.endswith('facebook.com/') and 'login' not in current_url)):
                logging.info("✅ Login verificado via URL")
                # Fazer verificação adicional mais simples
                email_form = await self.page.query_selector("input[name='email']")
                if not email_form:
                    logging.info("✅ Login confirmado - sem formulário de login")
                    await self._save_storage_state()
                    return True
            
            # Verificar se já está logado via elementos da página
            if await self._check_login_status():
                logging.info("✅ Já logado via sessão persistente")
                await self._save_storage_state()
                return True

            # Tentar login com cookies se disponíveis
            if await self._try_cookie_login():
                logging.info("✅ Login com cookies bem-sucedido")
                await self._save_storage_state()
                return True

            # Fallback para login manual
            logging.info("🔐 Necessário login manual...")
            if await self._perform_manual_login():
                logging.info("✅ Login manual concluído")
                await self._save_storage_state()
                return True

            return False

        except Exception as e:
            logging.error(f"❌ Erro no processo de login: {e}")
            return False

    async def _navigate_to_facebook(self, retries=3):
        """Navega para Facebook com retry."""
        for attempt in range(retries):
            try:
                logging.info(f"🌐 Navegando para Facebook (tentativa {attempt + 1}/{retries})")

                response = await self.page.goto(
                    FB_URL, 
                    wait_until='domcontentloaded',
                    timeout=30000
                )

                if response and response.status < 400:
                    await asyncio.sleep(3)  # Aguardar carregamento adicional
                    return True

            except Exception as e:
                logging.warning(f"⚠️ Tentativa {attempt + 1} falhou: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    continue

        logging.error("❌ Falha ao navegar para Facebook após múltiplas tentativas")
        return False

    async def _check_login_status(self) -> bool:
        """Verifica se o usuário está logado com validação mais rigorosa."""
        try:
            # Verificar ausência do formulário de login
            email_form = await self.page.query_selector("input[name='email']")
            
            # Se há formulário de login, definitivamente não está logado
            if email_form:
                logging.info("❌ Formulário de login detectado - não logado")
                return False

            # Verificar URL atual para determinar contexto
            current_url = self.page.url.lower()
            
            # Se está na home page, usar verificações específicas
            if '/home.php' in current_url or current_url.endswith('facebook.com/'):
                # Na home, verificar elementos específicos da timeline
                home_indicators = [
                    "div[role='main']",  # Container principal
                    "div[role='navigation']",  # Navegação superior
                    "div[data-pagelet='Feed']",  # Feed da timeline
                    "div[aria-label*='Facebook']",  # Logo do Facebook
                    "[data-testid='royal_login_form']"  # Este NÃO deve existir se logado
                ]
                
                # Verificar se NÃO há formulário de login
                login_form = await self.page.query_selector("[data-testid='royal_login_form']")
                if login_form:
                    logging.info("❌ Formulário real de login detectado na home")
                    return False
                
                # Verificar se há pelo menos um indicador de home logada
                for indicator in home_indicators[:4]:  # Excluir o último que é negativo
                    try:
                        element = await self.page.query_selector(indicator)
                        if element:
                            logging.info(f"✅ Login confirmado via elemento home: {indicator}")
                            return True
                    except Exception:
                        continue
                        
                # Se chegou aqui, assumir que está logado na home (pode estar carregando)
                logging.info("✅ Login assumido - página home sem formulário de login")
                return True
            
            # Se está em outras páginas (grupos, perfil, etc)
            else:
                # Verificar presença de elementos de navegação
                navigation = await self.page.query_selector("div[role='navigation']")
                left_menu = await self.page.query_selector("div[data-testid='left_nav_menu_list']")
                main_content = await self.page.query_selector("div[role='main']")
                
                # Considera logado se há navegação OU conteúdo principal
                is_logged_in = navigation or left_menu or main_content
                
                if is_logged_in:
                    logging.info("✅ Login confirmado - elementos de navegação disponíveis")
                else:
                    logging.warning("❌ Elementos de login não encontrados")
                
                return is_logged_in

        except Exception as e:
            logging.error(f"Erro ao verificar status de login: {e}")
            # Em caso de erro, verificar se pelo menos não há formulário de login
            try:
                email_form = await self.page.query_selector("input[name='email']")
                return not email_form
            except Exception:
                return False

    async def _try_cookie_login(self):
        """Tenta login com cookies salvos."""
        try:
            cookies = self._load_cookies()
            if not cookies:
                return False

            logging.info("🍪 Tentando login automático com cookies...")

            # Aplicar cookies
            await self.context.add_cookies(cookies)

            # Recarregar página para ativar cookies
            await self.page.reload(wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(5)

            # Verificar se funcionou
            return await self._check_login_status()

        except Exception as e:
            logging.warning(f"⚠️ Erro no login com cookies: {e}")
            return False

    def _load_cookies(self):
        """Carrega cookies do arquivo."""
        try:
            if not Path(COOKIES_FILE).exists():
                return None

            with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
                cookies_data = json.load(f)

            # Normalizar formato de cookies
            if isinstance(cookies_data, dict):
                cookies = cookies_data.get('all') or cookies_data.get('essential') or cookies_data
            elif isinstance(cookies_data, list):
                cookies = cookies_data
            else:
                return None

            logging.info(f"🍪 Carregados {len(cookies)} cookies")
            return cookies

        except Exception as e:
            logging.error(f"❌ Erro ao carregar cookies: {e}")
            return None

    async def _perform_manual_login(self):
        """Realiza login manual com tratamento de consentimentos."""
        try:
            # Ir para página de login se necessário
            if 'login' not in self.page.url:
                await self.page.goto("https://web.facebook.com/login", wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(3)

            logging.warning("🔐 ATENÇÃO: Login manual necessário!")
            logging.info("👆 Faça login no navegador aberto")
            logging.info("📱 Use suas credenciais normais")
            logging.info("⏳ Aguardando login... (timeout: 15 minutos)")

            # Aguardar login com verificação periódica
            for i in range(900):  # 15 minutos
                if i % 60 == 0 and i > 0:
                    minutes = i // 60
                    logging.info(f"⏳ {minutes} minuto(s) aguardando...")

                # Verificar login
                if await self._check_login_status():
                    logging.info("✅ Login manual detectado!")

                    # Tratar consentimentos/popups
                    await self._handle_consent_popups()

                    return True

                # Verificar se precisa tratar checkpoint/2FA
                if await self._check_checkpoint():
                    logging.error("❌ Checkpoint/2FA detectado - resolva manualmente")
                    continue

                await asyncio.sleep(1)

            logging.error("❌ Timeout no login manual")
            return False

        except Exception as e:
            logging.error(f"❌ Erro no login manual: {e}")
            return False

    async def _handle_consent_popups(self):
        """Trata popups de consentimento após login."""
        try:
            popups_to_handle = [
                # Cookies/consent banners
                ("button:has-text('Accept All')", "Accept All"),
                ("button:has-text('Aceitar todos')", "Aceitar todos"),
                ("button:has-text('Allow all cookies')", "Allow all cookies"),

                # Save browser/device
                ("button:has-text('Save Browser')", "Save Browser"),
                ("button:has-text('Salvar navegador')", "Salvar navegador"),
                ("button:has-text('Not now')", "Not now"),
                ("button:has-text('Agora não')", "Agora não"),

                # Notifications
                ("button:has-text('Turn on')", "Turn on notifications"),
                ("button:has-text('Ativar')", "Ativar notificações"),
                ("button:has-text('No thanks')", "No thanks"),
                ("button:has-text('Não, obrigado')", "Não, obrigado"),

                # Generic dismiss
                ("button[aria-label='Close'], button[aria-label='Fechar']", "Close/Fechar")
            ]

            for selector, description in popups_to_handle:
                try:
                    element = await self.page.wait_for_selector(selector, timeout=3000)
                    if element and await element.is_visible():
                        logging.info(f"🔄 Tratando popup: {description}")
                        await element.click()
                        await asyncio.sleep(2)
                except Exception:
                    continue

        except Exception as e:
            logging.debug(f"Erro ao tratar popups: {e}")

    async def _check_checkpoint(self):
        """Verifica se está em checkpoint/2FA."""
        try:
            current_url = self.page.url.lower()
            
            # Verificações específicas de URL (mais confiáveis)
            url_checkpoint_indicators = [
                "/checkpoint/",
                "/2fa/",
                "/security/",
                "checkpoint.php",
                "two_factor"
            ]
            
            # Se a URL contém indicadores específicos, é checkpoint
            if any(indicator in current_url for indicator in url_checkpoint_indicators):
                return True
            
            # Se está na home ou em grupos, provavelmente não é checkpoint
            if ('/home.php' in current_url or 
                '/groups/' in current_url or 
                current_url.endswith('facebook.com/')):
                return False
            
            # Verificação adicional por elementos da página (apenas se URL não for conclusiva)
            try:
                # Procurar por elementos específicos de checkpoint
                checkpoint_elements = [
                    "[data-testid='checkpoint_title']",
                    "div:has-text('Security Check')",
                    "div:has-text('Verificação de Segurança')",
                    "div:has-text('Two-Factor Authentication')",
                    "div:has-text('Autenticação de dois fatores')"
                ]
                
                for selector in checkpoint_elements:
                    element = await self.page.query_selector(selector)
                    if element and await element.is_visible():
                        return True
                        
            except Exception:
                pass
            
            return False

        except Exception:
            return False

    async def _save_storage_state(self):
        """Salva storage state para reutilização."""
        try:
            storage_state_path = Path(STORAGE_STATE_FILE)
            storage_state_path.parent.mkdir(parents=True, exist_ok=True)

            await self.context.storage_state(path=str(storage_state_path))
            logging.info("💾 Storage state salvo")

        except Exception as e:
            logging.warning(f"⚠️ Erro ao salvar storage state: {e}")

    async def navigate_to_group(self, group_url: str):
        """Navega para grupo com retry e verificação de sessão."""
        try:
            # Verificar se ainda está logado antes de navegar
            if not await self._check_login_status():
                logging.warning("⚠️ Sessão perdida, re-estabelecendo login...")
                if not await self.ensure_logged_in():
                    raise Exception("Falha ao re-estabelecer login")

            logging.info(f"🌍 Navegando para grupo: {group_url}")

            # Navegar com retry
            for attempt in range(3):
                try:
                    response = await self.page.goto(
                        group_url, 
                        wait_until='domcontentloaded',
                        timeout=30000
                    )

                    if response and response.status < 400:
                        break

                except Exception as e:
                    logging.warning(f"⚠️ Tentativa {attempt + 1} falhou: {e}")
                    if attempt < 2:
                        await asyncio.sleep(5)
                        continue
                    else:
                        raise

            # Aguardar feed carregar com timeout aumentado
            try:
                await self.page.wait_for_selector("div[role='feed']", timeout=30000)
                await asyncio.sleep(3)
                logging.info("✅ Grupo carregado com sucesso")
            except Exception as e:
                logging.warning(f"⚠️ Feed demorou para carregar: {e}")
                # Tentar aguardar outros indicadores de carregamento
                try:
                    await self.page.wait_for_selector("article[role='article'], div[data-pagelet^='FeedUnit_']", timeout=15000)
                    logging.info("✅ Conteúdo do grupo detectado")
                except Exception:
                    logging.error("❌ Timeout no carregamento do grupo")

        except Exception as e:
            logging.error(f"❌ Erro ao navegar para grupo: {e}")
            raise

    def get_page(self) -> Page:
        """Retorna a página atual."""
        return self.page

async def fb_login(headless: bool = False):
    """Função principal de login robusta."""
    login_manager = PlaywrightFBLogin(headless=headless)
    try:
        await login_manager.__aenter__()
        return login_manager
    except Exception as e:
        logging.error(f"❌ Falha crítica no login: {e}")
        try:
            await login_manager.__aexit__(None, None, None)
        except Exception:
            pass
        return None