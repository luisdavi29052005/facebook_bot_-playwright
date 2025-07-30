
"""
Configuração avançada para evasão de detecção de automação.
Permite ajustes finos sem modificar o código principal.
"""

# User Agents mais realistas e atualizados
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
]

# Viewports realistas
VIEWPORTS = [
    {'width': 1920, 'height': 1080},
    {'width': 1366, 'height': 768},
    {'width': 1536, 'height': 864},
    {'width': 1440, 'height': 900}
]

# Headers HTTP realistas
HTTP_HEADERS = {
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Cache-Control': 'max-age=0',
    'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1'
}

# Argumentos do Chrome para máximo stealth
CHROME_ARGS = [
    # Básico
    '--no-first-run',
    '--no-service-autorun',
    '--password-store=basic',
    '--use-mock-keychain',
    '--no-default-browser-check',
    
    # Performance
    '--disable-background-timer-throttling',
    '--disable-backgrounding-occluded-windows',
    '--disable-renderer-backgrounding',
    '--disable-background-networking',
    '--disable-background-mode',
    
    # Features/Extensions
    '--disable-features=TranslateUI,BlinkGenPropertyTrees',
    '--disable-component-extensions-with-background-pages',
    '--disable-default-apps',
    '--disable-extensions',
    '--disable-sync',
    
    # Automação
    '--disable-blink-features=AutomationControlled',
    '--disable-client-side-phishing-detection',
    '--disable-component-update',
    '--disable-domain-reliability',
    '--disable-hang-monitor',
    '--disable-ipc-flooding-protection',
    
    # Segurança (para sites que requerem)
    '--disable-web-security',
    '--allow-running-insecure-content',
    '--ignore-certificate-errors',
    '--ignore-ssl-errors',
    '--ignore-certificate-errors-spki-list',
    
    # UI
    '--disable-popup-blocking',
    '--disable-prompt-on-repost',
    '--disable-notifications',
    '--mute-audio',
    
    # Recursos gráficos
    '--disable-features=VizDisplayCompositor,VizServiceDisplay',
    '--disable-gpu-sandbox',
    '--no-sandbox',
    
    # Logs
    '--disable-logging',
    '--log-level=3',
    '--silent',
    
    # Performance adicional
    '--metrics-recording-only',
    '--no-report-upload',
    '--disable-dev-shm-usage'
]

# Script JavaScript para injeção stealth
STEALTH_SCRIPT = """
// === STEALTH INJECTION SCRIPT ===

// 1. Remover webdriver property
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
});

// 2. Mascarar chrome object
Object.defineProperty(window, 'chrome', {
    get: () => ({
        runtime: {},
        loadTimes: function() {},
        csi: function() {},
        app: {},
    }),
});

// 3. Simular plugins reais
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        {
            0: { type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format", filename: "internal-pdf-viewer" },
            description: "Portable Document Format",
            filename: "internal-pdf-viewer",
            length: 1,
            name: "Chrome PDF Plugin"
        },
        {
            0: { type: "application/pdf", suffixes: "pdf", description: "Portable Document Format", filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai" },
            description: "Portable Document Format",
            filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
            length: 1,
            name: "Chrome PDF Viewer"
        }
    ],
});

// 4. Languages realistas
Object.defineProperty(navigator, 'languages', {
    get: () => ['pt-BR', 'pt', 'en-US', 'en'],
});

// 5. Mascarar permissions
if (navigator.permissions && navigator.permissions.query) {
    const originalQuery = navigator.permissions.query;
    navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );
}

// 6. Adicionar propriedades ausentes
if (!window.outerHeight) {
    window.outerHeight = window.innerHeight;
}
if (!window.outerWidth) {
    window.outerWidth = window.innerWidth;
}

// 7. WebGL fingerprinting
const getParameter = WebGLRenderingContext.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    // UNMASKED_VENDOR_WEBGL
    if (parameter === 37445) {
        return 'Intel Inc.';
    }
    // UNMASKED_RENDERER_WEBGL  
    if (parameter === 37446) {
        return 'Intel(R) UHD Graphics 620';
    }
    return getParameter.call(this, parameter);
};

// 8. Canvas fingerprinting
const toDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(...args) {
    const context = this.getContext('2d');
    if (context) {
        // Adicionar ruído mínimo
        const imageData = context.getImageData(0, 0, this.width, this.height);
        for (let i = 0; i < imageData.data.length; i += 4) {
            imageData.data[i] = imageData.data[i] + Math.floor(Math.random() * 2);
        }
        context.putImageData(imageData, 0, 0);
    }
    return toDataURL.apply(this, args);
};

// 9. Remove automation traces
delete window._phantom;
delete window.__nightmare;
delete window._selenium;
delete window.callPhantom;
delete window.callSelenium;
delete window.__webdriver_script_fn;

// 10. Mock missing properties
if (!navigator.connection) {
    Object.defineProperty(navigator, 'connection', {
        get: () => ({
            effectiveType: '4g',
            rtt: 50,
            downlink: 10,
            addEventListener: () => {},
            removeEventListener: () => {}
        }),
    });
}

console.log('🥷 Stealth mode activated');
"""

# Configurações de timing para comportamento humano
HUMAN_TIMING = {
    'page_load_wait': (3, 8),          # Aguardar entre 3-8s após carregar página
    'interaction_delay': (0.5, 2.0),   # Delay entre interações
    'typing_speed': (50, 150),          # Velocidade de digitação (ms por char)
    'scroll_delay': (1, 3),             # Delay entre scrolls
    'click_delay': (0.1, 0.5)           # Delay antes de clicar
}

# URLs para teste de detecção
DETECTION_TEST_URLS = [
    'https://bot.sannysoft.com/',
    'https://arh.antoinevastel.com/bots/areyouheadless',
    'https://pixelscan.net/'
]
