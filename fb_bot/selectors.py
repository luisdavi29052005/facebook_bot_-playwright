"""
Facebook selectors configuration with robustness improvements.
Uses ARIA attributes, roles, and multiple fallbacks to handle UI changes.
"""

class FacebookSelectors:
    """Facebook page selectors with multiple fallbacks."""

    # Post container selectors - prioritize semantic attributes
    POST_CONTAINERS = [
        '[role="article"]',  # Semantic role
        '[data-pagelet="FeedUnit"]',  # Facebook data attribute
        '[data-testid="fbfeed_story"]',  # Test ID attribute
        '.x1yztbdb.x1n2onr6.xh8yej3.x1ja2u2z',  # Class fallback
        '.x1lliihq.x1plvlek.xryxfnj.x1n2onr6.x193iq5w.xeuugli.x1fj9vlw.x13faqbe.x1vvkbs.x1s928wv.xhkezso.x1gmr53x.x1cpjm7i.x1fgarty.x1943h6x.x1i0vuye.xvs91rp.xo1l8bm.x5n08af.x10wh9bi.x1wdrske.x8viiok.x18hxmgj'
    ]

    # Author name selectors
    AUTHOR_SELECTORS = [
        '[role="link"] strong',  # Link with strong text (name)
        'h3 [role="link"]',  # Header link
        'h3 strong a',  # Header strong link
        '[data-hovercard-prefer-more-content-show="1"] strong',  # Hovercard attribute
        '.x1heor9g.x1qlqyl8.x1pd3egz.x1a2a7pz strong',  # Class fallback
        'strong[dir="auto"]',  # Strong with dir attribute
        'a[role="link"] > span > span'  # Nested span structure
    ]

    # Post text content selectors
    TEXT_SELECTORS = [
        '[data-ad-preview="message"]',  # Data attribute for message
        '[data-testid="post_message"]',  # Test ID for post message
        '[role="article"] [dir="auto"]',  # Article with dir attribute
        '.x11i5rnm.xat24cr.x1mh8g0r.x1vvkbs',  # Class fallback
        '.xdj266r.x14z9mp.xat24cr.x1lziwak.x1vvkbs'
    ]

    # Image selectors
    IMAGE_SELECTORS = [
        'img[data-visualcompletion="media-vc-image"]',  # Visual completion attribute
        '[role="img"] img',  # Image role
        '.x85a59c.x193iq5w img',  # Class with img
        'img[src*="scontent"]',  # Facebook CDN pattern
        'img[alt]:not([alt=""])'  # Images with alt text
    ]

    # Video selectors
    VIDEO_SELECTORS = [
        'video[data-video-feature]',  # Video with data attribute
        '[role="button"][aria-label*="play" i]',  # Play button
        '.x1lliihq.x5yr21d.xh8yej3 video',  # Class with video
        '[data-testid="video-component"]'  # Test ID for video
    ]

    # Comment box selectors
    COMMENT_BOX_SELECTORS = [
        '[role="textbox"][aria-label*="comment" i]',  # Textbox role with comment label
        '[data-testid="fb-composer-text-area"]',  # Test ID for composer
        '[contenteditable="true"][aria-label*="comment" i]',  # Contenteditable with comment
        'div[role="textbox"][data-contents="true"]',  # Textbox with data-contents
        '.x1i10hfl.xggy1nq.x1s07b3s.x1kdt53j.x1a2a7pz'  # Class fallback
    ]

    # Comment submit button selectors
    COMMENT_SUBMIT_SELECTORS = [
        '[role="button"][aria-label*="comment" i]',  # Button role with comment
        '[data-testid="comment-submit"]',  # Test ID for submit
        'div[role="button"][tabindex="0"]:has-text("Comment")',  # Button with Comment text
        '.x1i10hfl.xjbqb8w.x1ejq31n.xd10rxx.x1sy0etr.x17r0tee.x972fbf.xcfux6l.x1qhh985.xm0m39n.x9f619.x1ypdohk.xe8uvvx.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.x16tdsg8.x1hl2dhg.xggy1nq.x87ps6o.x1lku1pv.x1a2a7pz.x6s0dn4.xmjcpbm.x107yiy2.xv8uw2v.x1tfwpuw.x2g32xy.x78zum5.x1q0g3np.x1iyjqo2.x1nhvcw1.x1n2onr6.x14atkfc.xcdnw81.x1ldfrly.x1 data:has([tabindex="0"])'
    ]

    # More options (three dots) selectors
    MORE_OPTIONS_SELECTORS = [
        '[role="button"][aria-label*="more" i]',  # Button with "more" label
        '[aria-label*="Action" i][role="button"]',  # Action button
        'div[role="button"][aria-haspopup="menu"]',  # Button with menu popup
        '.x1i10hfl.xjbqb8w.x1ejq31n.xd10rxx.x1sy0etr.x17r0tee.x972fbf.xcfux6l.x1qhh985.xm0m39n.x9f619.x1ypdohk.xe8uvvx.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.x16tdsg8.x1hl2dhg.xggy1nq.x87ps6o.x1lku1pv.x1a2a7pz.x6s0dn4.x1ejq31n.xd10rxx.x1sy0etr.x17r0tee.x972fbf.xcfux6l.x1qhh985.xm0m39n.x9f619.x1ypdohk.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.x1hl2dhg.xggy1nq.x87ps6o.x1lku1pv.x1a2a7pz.xbtce8p.x14atkfc.x1d5rgwi'
    ]

    # "See more" text indicators to filter out
    SEE_MORE_PATTERNS = [
        "see more",
        "ver mais", 
        "voir plus",
        "más",
        "show more",
        "mostrar mais"
    ]

    # Invalid author patterns (timestamps, UI elements)
    INVALID_AUTHOR_PATTERNS = [
        r'^\d+\s*(min|h|hr|hrs|d|dia|dias|hora|horas|s|sec|seconds)$',
        r'^\d+\s*(min|h|hr|hrs|d|dia|dias|hora|horas|s|sec|seconds)\s*(ago|atrás)?$',
        r'^(há|ago)\s+\d+',
        r'^(like|comment|share|curtir|comentar|compartilhar)$',
        r'^\d+$',  # Just numbers
        r'^(sponsored|patrocinado)$'  # Sponsored content
    ]

    @classmethod
    def get_post_containers(cls):
        """Get post container selectors in priority order."""
        return cls.POST_CONTAINERS

    @classmethod
    def get_author_selectors(cls):
        """Get author name selectors in priority order."""
        return cls.AUTHOR_SELECTORS

    @classmethod
    def get_text_selectors(cls):
        """Get post text selectors in priority order."""
        return cls.TEXT_SELECTORS

    @classmethod
    def get_image_selectors(cls):
        """Get image selectors in priority order."""
        return cls.IMAGE_SELECTORS

    @classmethod
    def get_video_selectors(cls):
        """Get video selectors in priority order."""
        return cls.VIDEO_SELECTORS

    @classmethod
    def get_comment_box_selectors(cls):
        """Get comment box selectors in priority order."""
        return cls.COMMENT_BOX_SELECTORS

    @classmethod
    def get_comment_submit_selectors(cls):
        """Get comment submit button selectors in priority order."""
        return cls.COMMENT_SUBMIT_SELECTORS

    @classmethod
    def get_more_options_selectors(cls):
        """Get more options button selectors in priority order."""
        return cls.MORE_OPTIONS_SELECTORS