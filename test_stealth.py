
import asyncio
import logging
from fb_bot.login import PlaywrightFBLogin

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_stealth():
    """Script robusto para testar configuração stealth."""
    print("🧪 Testando configuração stealth avançada...")
    
    login_manager = PlaywrightFBLogin(headless=False)
    
    try:
        # Usar context manager
        async with login_manager:
            page = login_manager.get_page()
            
            print("📱 Navegando para Facebook...")
            
            # Navegar manualmente para ter mais controle
            await page.goto("https://www.facebook.com", wait_until='load', timeout=60000)
            await asyncio.sleep(5)
            
            # Verificações detalhadas
            detection_results = await page.evaluate("""
                () => {
                    const results = {};
                    
                    // 1. Verificar webdriver
                    results.webdriver_detected = navigator.webdriver !== undefined;
                    
                    // 2. Verificar chrome automation
                    results.chrome_automation = window.chrome && 
                        window.chrome.runtime && 
                        window.chrome.runtime.onConnect;
                    
                    // 3. Verificar CSS carregado
                    const body = document.body;
                    if (body) {
                        const style = window.getComputedStyle(body);
                        const bgColor = style.backgroundColor;
                        const textColor = style.color;
                        
                        results.css_loaded = document.styleSheets.length > 0;
                        results.has_styles = bgColor !== 'rgba(0, 0, 0, 0)' && 
                                           bgColor !== 'transparent';
                        results.facebook_styled = !(bgColor === 'rgb(255, 255, 255)' && 
                                                   textColor === 'rgb(0, 0, 0)');
                        results.background_color = bgColor;
                        results.text_color = textColor;
                        results.stylesheets_count = document.styleSheets.length;
                    }
                    
                    // 4. Verificar elementos do Facebook
                    results.facebook_elements = {
                        has_login_form: !!document.querySelector('input[name="email"]'),
                        has_logo: !!document.querySelector('[aria-label*="Facebook"]'),
                        has_navigation: !!document.querySelector('[role="navigation"]')
                    };
                    
                    // 5. User agent
                    results.user_agent = navigator.userAgent;
                    
                    return results;
                }
            """)
            
            # Exibir resultados
            print(f"\n📊 RESULTADOS DA DETECÇÃO:")
            print(f"   🤖 Webdriver detectado: {detection_results.get('webdriver_detected', 'N/A')}")
            print(f"   🔧 Chrome automation: {detection_results.get('chrome_automation', 'N/A')}")
            print(f"   🎨 CSS carregado: {detection_results.get('css_loaded', 'N/A')}")
            print(f"   ✨ Tem estilos: {detection_results.get('has_styles', 'N/A')}")
            print(f"   📘 Facebook styled: {detection_results.get('facebook_styled', 'N/A')}")
            print(f"   🎨 Background: {detection_results.get('background_color', 'N/A')}")
            print(f"   📝 Text color: {detection_results.get('text_color', 'N/A')}")
            print(f"   📄 Stylesheets: {detection_results.get('stylesheets_count', 'N/A')}")
            
            fb_elements = detection_results.get('facebook_elements', {})
            print(f"\n🏗️ ELEMENTOS DO FACEBOOK:")
            print(f"   📝 Form de login: {fb_elements.get('has_login_form', 'N/A')}")
            print(f"   🏷️ Logo Facebook: {fb_elements.get('has_logo', 'N/A')}")
            print(f"   🧭 Navegação: {fb_elements.get('has_navigation', 'N/A')}")
            
            # Avaliar sucesso
            css_success = (detection_results.get('css_loaded', False) and 
                          detection_results.get('has_styles', False) and
                          detection_results.get('facebook_styled', False))
            
            stealth_success = (not detection_results.get('webdriver_detected', True) and
                             not detection_results.get('chrome_automation', True))
            
            if css_success and stealth_success:
                print("✅ SUCESSO: Stealth funcionando e CSS carregado!")
            elif css_success:
                print("⚠️ PARCIAL: CSS carregado, mas detecção pode estar ativa")
            elif stealth_success:
                print("⚠️ PARCIAL: Stealth OK, mas CSS não carregou")
            else:
                print("❌ FALHA: Facebook detectou automação e bloqueou CSS")
            
            # Aguardar para inspeção manual
            print(f"\n⏳ Deixando página aberta por 60 segundos para inspeção...")
            print(f"   👀 Verifique se a página parece normal (com cores e layout)")
            print(f"   🔍 URL atual: {page.url}")
            
            await asyncio.sleep(60)
                
    except Exception as e:
        print(f"❌ Erro durante teste: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_stealth())
