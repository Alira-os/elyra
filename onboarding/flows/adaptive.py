from onboarding.flows.questions import (
    get_next_question, get_summary_text, PLATFORM_TASK_MAP
)
from skills.executable.platform_detector import detect_platform
from registry.registry import load_persona
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class TaskContext:
    url: Optional[str] = None
    platform: str = "generic"
    platform_confidence: float = 0.0
    task_type: str = "generic"
    stack_preference: str = "modernize"
    stack_notes: str = ""
    must_haves: list = field(default_factory=list)
    migrate_products: bool = False
    migrate_articles: bool = False
    user_description: str = ""
    user_reference_url: Optional[str] = None
    onboarding_complete: bool = False
    onboarding_questions_asked: int = 0
    answers: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "platform": self.platform,
            "platform_confidence": self.platform_confidence,
            "task_type": self.task_type,
            "stack_preference": self.stack_preference,
            "stack_notes": self.stack_notes,
            "must_haves": self.must_haves,
            "migrate_products": self.migrate_products,
            "migrate_articles": self.migrate_articles,
            "user_description": self.user_description,
            "user_reference_url": self.user_reference_url,
            "onboarding_complete": self.onboarding_complete,
            "onboarding_questions_asked": self.onboarding_questions_asked
        }


class AdaptiveOnboarding:
    """
    Adaptive onboarding flow that asks up to 5 questions.

    The flow adapts based on answers:
    1. Site type → type-specific question
    2. Stack preference → optional notes
    3. Final confirmation

    After onboarding, produces a structured TaskContext.
    """

    def __init__(self):
        self.task_context = TaskContext()
        self.current_question = None
        self.questions_asked = 0

    def start(self, url: Optional[str] = None) -> dict:
        """
        Start onboarding with optional URL.

        Returns first question.
        """
        if url:
            self.task_context.url = url
            detection = detect_platform(url)
            self.task_context.platform = detection["platform"]
            self.task_context.platform_confidence = detection["confidence"]

            if detection["confidence"] < 0.5:
                self.task_context.platform = "generic"

        self.current_question = get_next_question({})
        self.questions_asked = 1
        return self._format_question(self.current_question)

    def answer(self, answer: str) -> dict:
        """
        Submit an answer and get next question or final result.

        Args:
            answer: User's answer value

        Returns:
            Next question dict or final TaskContext
        """
        if not self.current_question:
            return {"error": "Onboarding not started"}

        qid = self.current_question["id"]
        self.task_context.answers[qid] = answer
        self._apply_answer(qid, answer)

        if self.questions_asked >= 5:
            return self._finish_onboarding()

        next_q = self._get_next_question()
        if next_q is None:
            return self._finish_onboarding()

        if next_q.get("type") == "confirmation":
            return self._finish_onboarding()

        self.current_question = next_q
        self.questions_asked += 1
        self.task_context.onboarding_questions_asked = self.questions_asked

        return self._format_question(self.current_question)

    def _apply_answer(self, question_id: str, answer: str):
        if question_id == "site_type":
            self.task_context.task_type = PLATFORM_TASK_MAP.get(answer, "generic")
            if answer == "other":
                self.task_context.task_type = "generic"
        elif question_id.startswith("type_specific_"):
            if "e-commerce" in question_id:
                self.task_context.migrate_products = (answer == "same_products")
            elif "blog" in question_id:
                self.task_context.migrate_articles = (answer in ["all", "recent"])
                self.task_context.must_haves = ["blog"] if self.task_context.migrate_articles else []
            elif "portfolio" in question_id:
                self.task_context.must_haves = self._parse_portfolio_must_haves(answer)
            elif "business" in question_id:
                self.task_context.must_haves = self._parse_business_must_haves(answer)
        elif question_id == "stack_preference":
            self.task_context.stack_preference = answer
        elif question_id == "stack_notes":
            if answer and answer.strip():
                self.task_context.stack_notes = answer.strip()
                if not answer.startswith("http"):
                    self.task_context.user_description = answer.strip()
                else:
                    self.task_context.user_reference_url = answer.strip()

    def _parse_portfolio_must_haves(self, answer: str) -> list:
        mapping = {
            "images": ["home", "portfolio", "gallery"],
            "case_studies": ["home", "portfolio", "case-studies"],
            "structure": ["home", "about", "portfolio"]
        }
        return mapping.get(answer, ["home", "portfolio"])

    def _parse_business_must_haves(self, answer: str) -> list:
        mapping = {
            "standard": ["home", "about", "services", "contact"],
            "with_blog": ["home", "about", "services", "contact", "blog"],
            "with_gallery": ["home", "about", "services", "contact", "gallery"],
            "full": ["home", "about", "services", "contact", "blog", "gallery", "shop"]
        }
        return mapping.get(answer, ["home", "about", "services", "contact"])

    def _get_next_question(self) -> Optional[dict]:
        if self.current_question:
            return get_next_question(
                self.task_context.answers,
                self.current_question.get("next")
            )
        return get_next_question(self.task_context.answers)

    def _format_question(self, question: dict) -> dict:
        if question.get("type") == "text":
            return {
                "question": question["question"],
                "type": "text",
                "required": question.get("required", False),
                "placeholder": "Enter your description or a reference URL..."
            }
        elif question.get("type") == "confirmation":
            return {
                "question": question["question"],
                "summary": get_summary_text(self.task_context.to_dict()),
                "type": "confirmation",
                "required": True,
                "options": [
                    {"value": "yes", "label": "Yes, looks right"},
                    {"value": "no", "label": "No, let me correct something"}
                ]
            }
        else:
            return {
                "question": question["question"],
                "options": question.get("options", []),
                "required": question.get("required", True)
            }

    def _finish_onboarding(self) -> dict:
        self.task_context.onboarding_complete = True
        self.current_question = None
        return {
            "complete": True,
            "task_context": self.task_context.to_dict()
        }

    def get_next_question(self, answers_so_far: dict = None) -> dict:
        """
        Get next question without full answer flow (for simple invocation).
        """
        if answers_so_far is None:
            answers_so_far = self.task_context.answers

        next_q = get_next_question(answers_so_far)
        if next_q:
            return self._format_question(next_q)
        return {"done": True}


class OnboardingPersona:
    """
    Wrapper that loads persona definition from registry.
    """

    def __init__(self):
        self.persona = load_persona("onboarding_specialist")

    def get_system_prompt(self) -> str:
        return self.persona["content"]


if __name__ == "__main__":
    onboarding = AdaptiveOnboarding()

    print("=== Adaptive Onboarding Demo ===\n")

    print("Step 1: Start with URL")
    result = onboarding.start("https://photographer.wixsite.com/portfolio")
    print(f"Q: {result['question']}")
    print(f"Options: {[o['label'] for o in result.get('options', [])]}\n")

    print("Step 2: Answer site_type=portfolio")
    result = onboarding.answer("portfolio")
    print(f"Q: {result['question']}")
    print(f"Options: {[o['label'] for o in result.get('options', [])]}\n")

    print("Step 3: Answer portfolio_priority=images")
    result = onboarding.answer("images")
    print(f"Q: {result['question']}")
    print(f"Options: {[o['label'] for o in result.get('options', [])]}\n")

    print("Step 4: Answer stack_preference=modernize")
    result = onboarding.answer("modernize")
    print(f"Q: {result['question']}\n")

    print("Step 5: Answer stack_notes=Clean minimalist")
    result = onboarding.answer("Clean minimalist")
    print(f"Complete: {result.get('complete')}")
    print(f"Task context: {result.get('task_context')}")