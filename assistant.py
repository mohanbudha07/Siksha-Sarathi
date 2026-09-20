"""Student study assistant with Gemini and a safe offline fallback."""

import os


SYSTEM_INSTRUCTION = """
You are Siksha Sarathi, a supportive tutor for Nepal secondary-school students,
especially Grade 10. Explain concepts accurately in clear, age-appropriate
language. Use short steps and a small example when useful. Reply in Nepali when
the student asks in Nepali; otherwise reply in the language used by the student.
Help the student learn rather than completing a live examination for them. Never
claim certainty when unsure, and encourage checking the textbook or teacher for
school-specific curriculum details. Do not request personal or sensitive data.
Keep the answer focused and below 500 words.
""".strip()

DEFAULT_MODEL = "gemini-flash-latest"
MAX_ANSWER_LENGTH = 6000


def get_subject(question):
    question = question.lower()
    subjects = {
        "Science": [
            "cell", "plant", "animal", "physics", "chemical", "biology",
            "energy", "photosynthesis", "respiration", "ecosystem", "force",
            "motion", "science",
        ],
        "Mathematics": [
            "solve", "equation", "algebra", "number", "calculate",
            "percentage", "mathematics", "math",
        ],
        "English": ["grammar", "noun", "verb", "sentence", "meaning", "english"],
        "Social Studies": [
            "history", "government", "democracy", "culture", "social studies",
        ],
        "Nepali": ["munamadan", "nepali", "kabi", "sahitya", "नेपाली"],
    }

    for subject, words in subjects.items():
        if any(word in question for word in words):
            return subject
    return "General"


def generate_fallback_answer(question):
    """Return a small deterministic answer when Gemini is not available."""
    subject = get_subject(question)
    normalized_question = question.lower()
    knowledge = {
        "photosynthesis": (
            "Photosynthesis is the process in which green plants use sunlight, "
            "carbon dioxide and water to make glucose, releasing oxygen."
        ),
        "cell": "A cell is the basic structural and functional unit of life.",
        "democracy": (
            "Democracy is a system of government in which people choose their "
            "representatives through voting."
        ),
        "munamadan": (
            "Muna Madan is a famous Nepali narrative poem written by "
            "Laxmi Prasad Devkota."
        ),
    }

    for key, value in knowledge.items():
        if key in normalized_question:
            return subject, value

    return subject, (
        "The online tutor is unavailable, so I can only provide limited offline "
        "help for this question. Please ask about a specific concept such as "
        "photosynthesis, cells, democracy or Muna Madan, or ask your teacher."
    )


def generate_answer(question, client=None, api_key=None, model=None):
    """Return ``(subject, answer, mode)`` using Gemini when configured.

    ``client`` is injectable so tests never need network access. Any SDK, API,
    quota or empty-response failure falls back to the local study helper.
    """
    subject = get_subject(question)
    resolved_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")
    resolved_model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    owns_client = False

    if client is None and not resolved_key.strip():
        fallback_subject, answer = generate_fallback_answer(question)
        return fallback_subject, answer, "offline"

    try:
        if client is None:
            from google import genai

            client = genai.Client(api_key=resolved_key.strip())
            owns_client = True

        response = client.models.generate_content(
            model=resolved_model,
            contents=question,
            config={
                "system_instruction": SYSTEM_INSTRUCTION,
                "max_output_tokens": 700,
                "temperature": 0.3,
            },
        )
        answer = str(getattr(response, "text", "") or "").strip()
        if not answer:
            raise ValueError("Gemini returned an empty response")
        return subject, answer[:MAX_ANSWER_LENGTH], "gemini"
    except Exception:
        fallback_subject, answer = generate_fallback_answer(question)
        return fallback_subject, answer, "offline"
    finally:
        if owns_client and hasattr(client, "close"):
            client.close()
