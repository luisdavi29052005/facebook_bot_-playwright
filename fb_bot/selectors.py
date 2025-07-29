
import asyncio
import re
from playwright.async_api import Locator

# Seletores principais
ARTICLE = "div[role='article']"
FEED = "div[role='feed']"

# Regex para botões "Ver mais"
SEE_MORE_REGEX = r'(See more|Ver mais|Mostrar mais|Ver más|Voir plus)'

# Candidatos para mensagens do post
MESSAGE_CANDIDATES = [
    "[data-ad-preview='message'] div[dir='auto']",
    "[data-ad-comet-preview='message'] div[dir='auto']",
    "div[dir='auto']"
]

# Candidatos para imagens
IMG_CANDIDATE = "img[src*='scontent'], img[srcset*='scontent']"

# Seletores para posts válidos
POST_SELECTORS = [
    f"{FEED} {ARTICLE}",
    f"{FEED} div[class*='x1yztbdb']",
    "div[class*='userContentWrapper']",
    "div[data-testid*='story-subtitle'] >> xpath=ancestor::div[contains(@class, 'story_body_container')]",
    "div[class*='story_body_container']"
]

# Seletores para autor
AUTHOR_STRATEGIES = [
    [
        "h3 a[href*='facebook.com/'] strong",
        "h3 a[href*='/user/'] strong", 
        "h3 a[href*='/profile/'] strong",
        "h3 a[role='link'] strong:not(:has-text('·')):not(:has-text('min')):not(:has-text('h')):not(:has-text('d'))",
    ],
    [
        "h3 span[dir='auto']:not(:has-text('·')):not(:has-text('min')):not(:has-text('h')):not(:has-text('d')):not(:has-text('ago'))",
        "h3 span[class*='x1lliihq']:not(:has-text('·')):not(:has-text('min')):not(:has-text('h')):not(:has-text('d'))",
    ],
    [
        "h3 strong:not(:near(time)):not(:has-text('min')):not(:has-text('h')):not(:has-text('d')):not(:has-text('ago'))",
        "h3 span strong:not(:has-text('·')):not(:has-text('min'))",
    ]
]

# Seletores para texto do post
TEXT_STRATEGIES = [
    [
        "div[data-ad-preview='message']",
        "div[data-testid*='post_message']", 
        "div[class*='userContent']",
        "div[class*='text_exposed_root']",
    ],
    [
        "div[dir='auto']:not(:near(h3)):not(:near(time)) span[dir='auto']",
        "span[dir='auto']:not(:near(h3)):not(:near(time)):not(:has-text('Like')):not(:has-text('Comment'))",
        "div[class*='x1iorvi4']:not(:near(h3)) span[dir='auto']",
    ],
    [
        "div:not(:near(h3)):not([class*='comment']):not([class*='reaction']):not([class*='timestamp']) p",
        "div:not(:near(h3)):not([class*='comment']):not([class*='reaction']) span:not(:has-text('Like')):not(:has-text('Share'))",
    ]
]

# Seletores para imagens
IMAGE_STRATEGIES = [
    [
        "img[src*='scontent']:not([src*='profile']):not([src*='avatar'])",
        "img[src*='fbcdn']:not([src*='static']):not([src*='profile'])",
    ],
    [
        "img[class*='scaledImageFitWidth']",
        "img[class*='x1ey2m1c']:not([class*='profile']):not([src*='emoji'])",
        "img[referrerpolicy='origin-when-cross-origin']:not([src*='emoji']):not([src*='static'])",
    ],
    [
        "div[class*='uiScaledImageContainer'] img:not([src*='profile'])",
        "div[class*='_46-f'] img:not([src*='profile']):not([src*='avatar'])",
    ]
]

# Padrões para excluir do autor
AUTHOR_EXCLUDE_PATTERNS = [
    r'^\d+\s*(h|hr|hrs|min|mins|m|d|dia|dias|hora|horas|s|sec|seconds)$',
    r'^\d+\s*(h|hr|hrs|min|mins|m|d|dia|dias|hora|horas|s|sec|seconds)\s*(ago|atrás)?$',
    r'^(há|ago)\s+\d+',
    r'^(Like|Comment|Share|Curtir|Comentar|Compartilhar|Reply|Responder)$',
    r'^(Follow|Seguir|See More|Ver Mais|Most Relevant|Top Contributor)$',
    r'^·$',
    r'^\d+$',
    r'^\s*$',
]

# Padrões para excluir do texto
TEXT_EXCLUDE_PATTERNS = [
    r'^(Like|Comment|Share|Curtir|Comentar|Compartilhar|Responder|Reply)$',
    r'^(Follow|Seguir|See More|Ver Mais|Most Relevant|Top Contributor)$',
    r'^\d+\s*(like|curtir|comment|comentário|share|compartilhar)s?$',
    r'^\d+\s*(h|hr|hrs|min|mins|m|d|dia|dias|hora|horas)\s*(ago|atrás)?$',
    r'^(há|ago)\s+\d+',
    r'^·$',
    r'^\d+$',
    r'^(Translate|Traduzir|See Translation|Ver Tradução)$',
]

async def expand_article_text(article: Locator):
    """Expande o texto do artigo clicando no botão 'Ver mais' se existir."""
    try:
        see_more_button = article.get_by_role('button', name=re.compile(SEE_MORE_REGEX, re.IGNORECASE)).first
        if await see_more_button.count() > 0 and await see_more_button.is_visible():
            await see_more_button.click()
            await asyncio.sleep(1)  # Aguardar expansão do texto
            return True
    except Exception:
        pass  # Silencioso conforme solicitado
    return False
"""
Seletores CSS para elementos do Facebook.
Centralizados para facilitar manutenção quando o Facebook muda a interface.
"""

# Seletores principais para feed e posts
FEED = "div[role='feed']"
ARTICLE = "div[role='article'], article[role='article']"

# Seletores para diferentes tipos de posts - FOCANDO NA ÁREA REAL DE POSTS
POST_SELECTORS = [
    # Seletores mais amplos para capturar posts reais
    'div[role="article"]',
    'article[role="article"]', 
    'div[data-pagelet^="FeedUnit_"]',
    # Containers de post baseados em estrutura comum
    'div:has(> div > div > div > div > div h3)',  # Posts com cabeçalho h3
    'div:has(span[dir="auto"]:has(strong))',     # Posts com nome do autor
    # Posts que têm botões de curtir/comentar
    'div:has(div[role="button"]:has-text("Curtir"))',
    'div:has(div[role="button"]:has-text("Like"))',
    # Estrutura típica de posts do Facebook
    'div[class*="x1yztbdb"]',
    'div[class*="story_body_container"]',
    # Posts com timestamp visível
    'div:has(time)',
    'div:has(a[href*="story_fbid"])',
    # Fallback mais geral
    'div:has(img[src*="scontent"]):has(strong)'
]

# Estratégias para extração de autor - MELHORADAS para capturar nomes reais
AUTHOR_STRATEGIES = [
    # Links de perfil com texto do nome
    'h3 a[role="link"] span[dir="auto"]',
    'h3 a[role="link"] strong',
    'h3 strong a[role="link"]',
    'h3 span[dir="auto"] a[role="link"]',
    # Links diretos com href de perfil
    'a[href*="/profile.php"] span[dir="auto"]:not([aria-hidden="true"])',
    'a[href*="/user/"] span[dir="auto"]:not([aria-hidden="true"])',
    'a[href*="facebook.com/"] span[dir="auto"]:not([aria-hidden="true"])',
    # Estruturas mais genéricas mas comuns
    'strong a span[dir="auto"]',
    'span[dir="auto"] strong a',
    # Fallback para nomes em elementos strong
    'h3 strong:not(:has(a))',
    'strong:not(:near(time)):not(:has-text("min")):not(:has-text("h")):not(:has-text("d"))',
    # Seletores específicos para layout atual do Facebook
    'div[role="article"] h3 span[dir="auto"]:first-child',
    'div[role="article"] strong:first-of-type'
]

# Estratégias para extração de texto
TEXT_STRATEGIES = [
    'div[dir="auto"]:visible:not([aria-hidden="true"])',
    '[data-testid="post_message"] div[dir="auto"]',
    'div[data-ad-preview="message"] div[dir="auto"]'
]

# Candidatos para mensagens (fallback)
MESSAGE_CANDIDATES = [
    '[data-testid="post_message"]',
    'div[data-ad-preview="message"]',
    'div[class*="userContent"]',
    'div[dir="auto"]:not(button div):not(a div)'
]

# Estratégias para extração de imagens
IMAGE_STRATEGIES = [
    'img[src*="scontent"]',  # Imagens reais do Facebook
    'div[style*="background-image"][style*="scontent"]',  # Background images
    'svg image[href*="scontent"]'  # SVG images
]

# Padrões para excluir de autores
AUTHOR_EXCLUDE_PATTERNS = [
    r'^\d+\s*(h|hr|hrs|min|mins|m|d|dia|dias|hora|horas|s|sec|seconds)$',
    r'^\d+\s*(h|hr|hrs|min|mins|m|d|dia|dias|hora|horas|s|sec|seconds)\s*(ago|atrás)?$',
    r'^(há|ago)\s+\d+',
    r'^(Like|Comment|Share|Curtir|Comentar|Compartilhar|Reply|Responder)$',
    r'^(Follow|Seguir|See More|Ver Mais|Most Relevant|Top Contributor)$',
    r'^·+$',
    r'^\d+$',
    r'^\s*$'
]

# Padrões para excluir de texto
TEXT_EXCLUDE_PATTERNS = [
    'ver mais', 'see more', 'mostrar mais',
    'ver tradução', 'see translation',
    'curtir', 'comentar', 'compartilhar',
    'like', 'comment', 'share', 'reply'
]

# Seletores para botões "Ver mais"
SEE_MORE_SELECTORS = [
    'div[role="button"]:has-text("Ver mais")',
    'div[role="button"]:has-text("See more")',
    'span[role="button"]:has-text("Ver mais")',
    'span[role="button"]:has-text("See more")',
    '*[role="button"]:has-text("Ver mais")',
    '*[role="button"]:has-text("See more")'
]

# Seletores para comentários
COMMENT_BUTTON_SELECTORS = [
    'div[role="button"]:has-text("Comentar")',
    'div[role="button"]:has-text("Comment")',
    '[aria-label*="omment" i]',
    '[aria-label*="comentar" i]',
    '[data-testid*="comment"]'
]

COMMENT_TEXTBOX_SELECTORS = [
    'div[contenteditable="true"][role="textbox"]',
    'textarea[placeholder*="omment"], textarea[placeholder*="comentar"]',
    '[data-testid="UFI2CommentTextarea"]'
]

async def expand_article_text(article):
    """Expande texto do artigo clicando em 'Ver mais' se disponível."""
    try:
        for selector in SEE_MORE_SELECTORS:
            try:
                see_more = article.locator(selector).first()
                if await see_more.count() > 0 and await see_more.is_visible():
                    await see_more.click()
                    import asyncio
                    await asyncio.sleep(2)
                    return True
            except Exception:
                continue
        return False
    except Exception:
        return False
