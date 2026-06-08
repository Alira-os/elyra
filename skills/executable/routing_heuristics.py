ROUTING_RULES = {
    ("wix", "e-commerce"): [
        "scraper",
        "architect",
        "marketing",
        "designer",
        "builder",
    ],
    ("wix", "portfolio"): [
        "scraper",
        "architect",
        "marketing",
        "designer",
        "builder",
    ],
    ("wix", "blog"): [
        "scraper",
        "architect",
        "marketing",
        "designer",
        "builder",
    ],
    ("wix", "business"): [
        "scraper",
        "architect",
        "marketing",
        "designer",
        "builder",
    ],
    ("squarespace", "e-commerce"): [
        "scraper",
        "architect",
        "marketing",
        "designer",
        "builder",
    ],
    ("squarespace", "portfolio"): [
        "scraper",
        "architect",
        "marketing",
        "designer",
        "builder",
    ],
    ("squarespace", "blog"): [
        "scraper",
        "architect",
        "marketing",
        "designer",
        "builder",
    ],
    ("squarespace", "business"): [
        "scraper",
        "architect",
        "marketing",
        "designer",
        "builder",
    ],
    ("wordpress", "e-commerce"): [
        "scraper",
        "architect",
        "marketing",
        "designer",
        "builder",
    ],
    ("wordpress", "portfolio"): [
        "scraper",
        "architect",
        "marketing",
        "designer",
        "builder",
    ],
    ("wordpress", "blog"): [
        "scraper",
        "architect",
        "marketing",
        "designer",
        "builder",
    ],
    ("wordpress", "business"): [
        "scraper",
        "architect",
        "marketing",
        "designer",
        "builder",
    ],
    ("generic", "generic"): [
        "scraper",
        "architect",
        "marketing",
        "designer",
        "builder",
    ],
    ("generic", "portfolio"): [
        "scraper",
        "architect",
        "marketing",
        "designer",
        "builder",
    ],
    ("generic", "blog"): [
        "scraper",
        "architect",
        "marketing",
        "designer",
        "builder",
    ],
    ("generic", "e-commerce"): [
        "scraper",
        "architect",
        "marketing",
        "designer",
        "builder",
    ],
    ("generic", "business"): [
        "scraper",
        "architect",
        "marketing",
        "designer",
        "builder",
    ],
}

STACK_CHOICES = {
    ("wix", "e-commerce"): {"primary": "nextjs+tailwind+shopify", "alt": ["nuxt+vuetify+shopify"]},
    ("wix", "portfolio"): {"primary": "nextjs+tailwind+contentlayer", "alt": ["astro+tailwind"]},
    ("wix", "blog"): {"primary": "nextjs+tailwind+mdx", "alt": ["astro+contentlayer"]},
    ("wix", "business"): {"primary": "nextjs+tailwind", "alt": ["nuxt+tailwind"]},
    ("squarespace", "e-commerce"): {"primary": "nextjs+tailwind+shopify", "alt": ["nuxt+vuetify+shopify"]},
    ("squarespace", "portfolio"): {"primary": "nextjs+tailwind+contentlayer", "alt": ["astro+tailwind"]},
    ("squarespace", "blog"): {"primary": "nextjs+tailwind+mdx", "alt": ["astro+contentlayer"]},
    ("squarespace", "business"): {"primary": "nextjs+tailwind", "alt": ["nuxt+tailwind"]},
    ("wordpress", "e-commerce"): {"primary": "nextjs+tailwind+shopify", "alt": ["nuxt+vuetify+shopify"]},
    ("wordpress", "portfolio"): {"primary": "nextjs+tailwind+contentlayer", "alt": ["astro+tailwind"]},
    ("wordpress", "blog"): {"primary": "nextjs+tailwind+mdx", "alt": ["astro+contentlayer"]},
    ("wordpress", "business"): {"primary": "nextjs+tailwind", "alt": ["nuxt+tailwind"]},
    ("generic", "generic"): {"primary": "nextjs+tailwind", "alt": ["nuxt+tailwind"]},
    ("generic", "portfolio"): {"primary": "nextjs+tailwind+contentlayer", "alt": ["astro+tailwind"]},
    ("generic", "blog"): {"primary": "nextjs+tailwind+mdx", "alt": ["astro+contentlayer"]},
    ("generic", "e-commerce"): {"primary": "nextjs+tailwind+shopify", "alt": ["nuxt+vuetify+shopify"]},
    ("generic", "business"): {"primary": "nextjs+tailwind", "alt": ["nuxt+tailwind"]},
}

PLATFORM_TASK_KEYS_EXACT = [
    ("wix", "e-commerce"), ("wix", "portfolio"), ("wix", "blog"), ("wix", "business"),
    ("squarespace", "e-commerce"), ("squarespace", "portfolio"), ("squarespace", "blog"), ("squarespace", "business"),
    ("wordpress", "e-commerce"), ("wordpress", "portfolio"), ("wordpress", "blog"), ("wordpress", "business"),
]

PLATFORM_TASK_KEYS_PARTIAL = [
    ("wix", "generic"), ("squarespace", "generic"), ("wordpress", "generic"),
    ("generic", "e-commerce"), ("generic", "portfolio"), ("generic", "blog"), ("generic", "business"),
    ("generic", "generic"),
]


def get_routing_sequence(platform: str, task_type: str, confidence_threshold: float = 0.7) -> dict:
    """
    Get default routing sequence for platform + task_type.

    Args:
        platform: wix, squarespace, wordpress, generic
        task_type: e-commerce, blog, portfolio, business, generic
        confidence_threshold: Minimum confidence to accept routing without LLM override

    Returns:
        {
            "routing_sequence": list of persona names,
            "confidence": 0.0 - 1.0,
            "requires_override": bool,
            "fallback_available": bool,
            "stack_chosen": str
        }
    """
    key = (platform.lower(), task_type.lower())

    if key in ROUTING_RULES:
        return {
            "routing_sequence": ROUTING_RULES[key],
            "confidence": 1.0,
            "requires_override": False,
            "fallback_available": True,
            "stack_chosen": STACK_CHOICES.get(key, {}).get("primary", "nextjs+tailwind")
        }

    for pk, tk in PLATFORM_TASK_KEYS_EXACT:
        if pk == platform.lower():
            alt_key = (pk, "generic")
            if alt_key in ROUTING_RULES:
                return {
                    "routing_sequence": ROUTING_RULES[alt_key],
                    "confidence": 0.8,
                    "requires_override": False,
                    "fallback_available": True,
                    "stack_chosen": STACK_CHOICES.get(alt_key, {}).get("primary", "nextjs+tailwind")
                }

    for pk, tk in PLATFORM_TASK_KEYS_PARTIAL:
        if tk == task_type.lower() and "generic" not in pk:
            alt_key = (pk, task_type.lower())
            if alt_key in ROUTING_RULES:
                return {
                    "routing_sequence": ROUTING_RULES[alt_key],
                    "confidence": 0.6,
                    "requires_override": True,
                    "fallback_available": True,
                    "stack_chosen": STACK_CHOICES.get(alt_key, {}).get("primary", "nextjs+tailwind")
                }

    return {
        "routing_sequence": ROUTING_RULES[("generic", "generic")],
        "confidence": 0.5,
        "requires_override": True,
        "fallback_available": True,
        "stack_chosen": "nextjs+tailwind"
    }


def get_stack_choice(platform: str, task_type: str) -> str:
    """Get the default stack choice for platform + task_type."""
    result = get_routing_sequence(platform, task_type)
    return result["stack_chosen"]


if __name__ == "__main__":
    test_cases = [
        ("wix", "portfolio"),
        ("squarespace", "blog"),
        ("wordpress", "e-commerce"),
        ("generic", "business"),
        ("unknown", "unknown"),
    ]

    for platform, task_type in test_cases:
        result = get_routing_sequence(platform, task_type)
        print(f"({platform}, {task_type}) -> conf={result['confidence']:.1f}, override={result['requires_override']}")
        print(f"  routing: {' -> '.join(result['routing_sequence'])}")
        print(f"  stack: {result['stack_chosen']}")