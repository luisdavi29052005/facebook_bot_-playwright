
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
