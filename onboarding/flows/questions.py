from typing import Optional


QUESTIONS = [
    {
        "id": "site_type",
        "question": "What type of site is this?",
        "options": [
            {"value": "e-commerce", "label": "E-commerce (products, shopping cart, checkout)"},
            {"value": "blog", "label": "Blog (articles, posts, categories)"},
            {"value": "portfolio", "label": "Portfolio (visual showcase, minimal text)"},
            {"value": "business", "label": "Business (services, about page, contact)"},
            {"value": "other", "label": "Other (describe in next step)"}
        ],
        "required": True,
        "next": "type_specific"
    },
    {
        "id": "type_specific_e-commerce",
        "question": "What's important for your new store?",
        "options": [
            {"value": "same_products", "label": "Same products / inventory (I'll help transfer)"},
            {"value": "fresh_start", "label": "Fresh start with new products"},
            {"value": "design_only", "label": "Just the design/style I like, new products later"}
        ],
        "required": True,
        "next": "stack_preference"
    },
    {
        "id": "type_specific_blog",
        "question": "How many articles are you looking to migrate?",
        "options": [
            {"value": "all", "label": "All of them (50+)"},
            {"value": "recent", "label": "Just my recent posts (10-20)"},
            {"value": "selection", "label": "A selection (I'll specify which)"}
        ],
        "required": True,
        "next": "stack_preference"
    },
    {
        "id": "type_specific_portfolio",
        "question": "What matters most in your portfolio?",
        "options": [
            {"value": "images", "label": "Image quality and layout"},
            {"value": "case_studies", "label": "Case study details"},
            {"value": "structure", "label": "Keeping my existing pages structure"}
        ],
        "required": True,
        "next": "stack_preference"
    },
    {
        "id": "type_specific_business",
        "question": "What are the must-have pages?",
        "options": [
            {"value": "standard", "label": "Home, About, Services, Contact"},
            {"value": "with_blog", "label": "Standard + Blog"},
            {"value": "with_gallery", "label": "Standard + Gallery"},
            {"value": "full", "label": "Everything (blog, gallery, shop)"}
        ],
        "required": True,
        "next": "stack_preference"
    },
    {
        "id": "stack_preference",
        "question": "Is there a specific stack or look you're aiming for?",
        "options": [
            {"value": "keep_similar", "label": "Keep it similar to what I have now"},
            {"value": "modernize", "label": "Modernize (new design, same content)"},
            {"value": "fresh_start", "label": "Something completely different"}
        ],
        "required": True,
        "next": "stack_notes"
    },
    {
        "id": "stack_notes",
        "question": "Describe what you're envisioning, or share a reference URL:",
        "options": [],
        "required": False,
        "next": "final_confirm",
        "type": "text"
    },
    {
        "id": "final_confirm",
        "question": "Before I proceed, a quick summary:",
        "type": "confirmation",
        "required": True
    }
]

PLATFORM_TASK_MAP = {
    "e-commerce": "e-commerce",
    "blog": "blog",
    "portfolio": "portfolio",
    "business": "business",
    "other": "generic"
}


def get_next_question(answers_so_far: dict, next_id: Optional[str] = None) -> Optional[dict]:
    if not next_id:
        next_id = "site_type"

    for q in QUESTIONS:
        if q["id"] == next_id:
            if q["id"] == "type_specific_e-commerce" and answers_so_far.get("site_type") != "e-commerce":
                continue
            if q["id"] == "type_specific_blog" and answers_so_far.get("site_type") != "blog":
                continue
            if q["id"] == "type_specific_portfolio" and answers_so_far.get("site_type") != "portfolio":
                continue
            if q["id"] == "type_specific_business" and answers_so_far.get("site_type") != "business":
                continue
            return q

    return None


def get_question_by_id(question_id: str) -> Optional[dict]:
    for q in QUESTIONS:
        if q["id"] == question_id:
            return q
    return None


def get_summary_text(task_context: dict) -> str:
    lines = []
    lines.append(f"- Site: {task_context.get('url', 'new site')}")
    lines.append(f"- Type: {task_context.get('task_type', 'unknown')}")
    lines.append(f"- Stack: {task_context.get('stack_preference', 'not specified')}")
    if task_context.get("stack_notes"):
        lines.append(f"- Notes: {task_context['stack_notes']}")
    if task_context.get("must_haves"):
        lines.append(f"- Must-haves: {', '.join(task_context['must_haves'])}")
    return "\n".join(lines)


if __name__ == "__main__":
    answers = {}

    q = get_next_question(answers)
    print(f"Q1: {q['question']}")

    answers["site_type"] = "portfolio"
    q = get_next_question(answers, "type_specific_portfolio")
    print(f"Q2: {q['question']}")

    answers["portfolio_priority"] = "images"
    q = get_next_question(answers, "stack_preference")
    print(f"Q3: {q['question']}")

    answers["stack_preference"] = "modernize"
    q = get_next_question(answers, "stack_notes")
    print(f"Q4: {q['question']}")

    answers["stack_notes"] = "Clean minimalist design"
    q = get_next_question(answers, "final_confirm")
    print(f"Q5: {q['question']}")

    task_context = {
        "url": "https://example.wixsite.com",
        "task_type": "portfolio",
        "stack_preference": "modernize",
        "stack_notes": "Clean minimalist design"
    }
    print("\nSummary:")
    print(get_summary_text(task_context))