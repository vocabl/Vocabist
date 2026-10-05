"""Versioned, centralized AI prompt templates.

Keep large prompts here, not scattered across route handlers. Each template has
a version id so changes are traceable.
"""
from __future__ import annotations

from typing import List, Optional

# --------------------------------------------------------------------------- #
# Vocabulary generation
# --------------------------------------------------------------------------- #
VOCAB_GENERATION_V1 = "VOCAB_GENERATION_V1"

_CEFR_HINT = "A1, A2, B1, B2, C1 or C2"


def vocab_generation_system() -> str:
    return (
        "You are a meticulous English lexicographer generating vocabulary entries "
        "for a learning app. Return ONLY valid minified JSON. Never add commentary, "
        "markdown, or code fences. Every entry must be a real English word with an "
        "accurate definition."
    )


def vocab_generation_prompt(
    count: int,
    *,
    cefr: Optional[str] = None,
    topic: Optional[str] = None,
    part_of_speech: Optional[str] = None,
    exam: Optional[str] = None,
    vocabulary_type: Optional[str] = None,
    avoid: Optional[List[str]] = None,
    enrichment_level: str = "standard",
) -> str:
    constraints = []
    if cefr:
        constraints.append(f"CEFR level: {cefr}")
    if topic:
        constraints.append(f"topic/theme: {topic}")
    if part_of_speech and part_of_speech != "mixed":
        constraints.append(f"part of speech: {part_of_speech}")
    if vocabulary_type:
        constraints.append(f"vocabulary type: {vocabulary_type}")
    cons = ("; ".join(constraints)) or "general English vocabulary"

    avoid_txt = ""
    if avoid:
        sample = ", ".join(avoid[:60])
        avoid_txt = f"\nDo NOT include any of these existing words: {sample}."

    rich = ""
    if enrichment_level == "rich":
        rich = (
            ' "synonyms":["..."],"antonyms":["..."],"word_family":["..."],'
            '"mnemonic":"memory hook","common_mistakes":"a common mistake learners make",'
        )
    elif enrichment_level == "standard":
        rich = ' "synonyms":["..."],"antonyms":["..."],'

    exam_note = (
        f'Set "exam_relevance" to ["{exam}"] for every entry.'
        if exam else 'Leave "exam_relevance" as an empty array []. Never invent exam names.'
    )

    return (
        f"Generate {count} distinct English vocabulary entries. Constraints: {cons}.{avoid_txt}\n"
        f"{exam_note}\n"
        f"CEFR must be one of {_CEFR_HINT}.\n"
        'Return a JSON object of the exact shape: '
        '{"words":[{"headword":"word","part_of_speech":"noun",'
        '"cefr":"B2","simple_definition":"a clear one-sentence learner definition",'
        '"easy_meaning":"an even simpler paraphrase","example":"a natural example sentence",'
        f'{rich}"topic":"short topic label"}}]}}\n'
        "Rules: headword is a single lemma (lowercase), no duplicates, definitions must be "
        "accurate and self-contained, example must actually use the headword."
    )


# --------------------------------------------------------------------------- #
# Field-level enrichment / regeneration
# --------------------------------------------------------------------------- #
VOCAB_ENRICH_V1 = "VOCAB_ENRICH_V1"

_FIELD_SPECS = {
    "definition": ('simple_definition', 'a clear one-sentence learner definition (string)'),
    "examples": ('example', 'one natural example sentence that uses the word (string)'),
    "synonyms": ('synonyms', 'an array of 3-6 single-word synonyms (array of strings)'),
    "antonyms": ('antonyms', 'an array of 2-5 single-word antonyms (array of strings)'),
    "cefr": ('cefr', 'the single best CEFR level, one of A1 A2 B1 B2 C1 C2 (string)'),
    "word_family": ('word_family', 'an array of 2-6 morphologically related words (array of strings)'),
    "memory_hook": ('mnemonic', 'a short vivid memory hook (string)'),
    "common_mistake": ('common_mistakes', 'one common mistake learners make with this word (string)'),
}


def enrich_field_spec(field: str):
    return _FIELD_SPECS.get(field)


def enrich_field_system() -> str:
    return (
        "You improve a single field of an English vocabulary entry. Return ONLY valid "
        "minified JSON with exactly one key. No commentary, no markdown."
    )


def enrich_field_prompt(field: str, word: dict) -> Optional[str]:
    spec = _FIELD_SPECS.get(field)
    if not spec:
        return None
    json_key, desc = spec
    hw = word.get("headword")
    definition = word.get("simple_definition") or ""
    pos = word.get("part_of_speech") or ""
    return (
        f'For the English word "{hw}" (part of speech: {pos}; meaning: {definition}), '
        f'produce {desc}.\n'
        f'Return ONLY JSON: {{"{json_key}": <value>}}'
    )


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
CLASSIFY_V1 = "CLASSIFY_V1"


def classify_system() -> str:
    return "You classify English words. Return ONLY valid minified JSON. No commentary."


# --------------------------------------------------------------------------- #
# Translation
# --------------------------------------------------------------------------- #
TRANSLATE_V1 = "TRANSLATE_V1"


def translate_system(source: str, target: str) -> str:
    return (
        f"You are a professional translator. Translate the user's text from {source} to "
        f"{target}. Output ONLY the translated text, with no quotes, no notes, no explanation."
    )


# --------------------------------------------------------------------------- #
# Multimodal extraction
# --------------------------------------------------------------------------- #
MULTIMODAL_EXTRACT_V1 = "MULTIMODAL_EXTRACT_V1"


def multimodal_extract_system() -> str:
    return (
        "You extract study-worthy English vocabulary from an image (a textbook page, "
        "screenshot, chart, document, or study material). Focus on meaningful, "
        "difficult, academic, and exam-relevant vocabulary. "
        "Avoid names, URLs, numbers, common function words, and OCR noise. "
        "Return ONLY valid minified JSON. No commentary."
    )


def multimodal_extract_prompt(max_words: int = 15) -> str:
    return (
        f"Look at the image and extract up to {max_words} useful English vocabulary words a "
        "learner should study. Prioritize meaningful, difficult, academic, or exam-relevant words. "
        "For each word provide: an accurate short definition, CEFR level, part of speech, "
        "the context where you found it, your confidence (high/medium/low), and why it's worth studying.\n"
        'Return ONLY JSON: {"words":[{"headword":"word","cefr":"B2",'
        '"simple_definition":"clear definition","example":"natural example sentence",'
        '"part_of_speech":"noun","detected_context":"the sentence or context from the image",'
        '"confidence":"high","reason":"why this word is worth studying"}]}'
    )
