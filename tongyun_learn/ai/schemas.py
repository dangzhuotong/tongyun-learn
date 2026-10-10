import re
from typing import Any

from jsonschema import Draft202012Validator

KINDS: dict[str, dict[str, str]] = {
    "word_mnemonic": {"prompt_ver": "w1"},
    "sentence_grammar": {"prompt_ver": "s1"},
    "word_quiz": {"prompt_ver": "q1"},
}

WORD_MNEMONIC_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "word",
        "phonetic",
        "meanings",
        "examples",
        "roots",
        "etymology",
        "mnemonic",
        "related",
    ],
    "properties": {
        "word": {"type": "string"},
        "phonetic": {"type": "string"},
        "meanings": {
            "type": "array",
            "minItems": 1,
            "maxItems": 6,
            "items": {
                "type": "object",
                "required": ["pos", "cn"],
                "properties": {
                    "pos": {"type": "string"},
                    "cn": {"type": "string"},
                },
            },
        },
        "examples": {
            "type": "array",
            "minItems": 2,
            "maxItems": 3,
            "items": {
                "type": "object",
                "required": ["en", "zh"],
                "properties": {
                    "en": {"type": "string", "minLength": 3},
                    "zh": {"type": "string", "minLength": 1},
                },
            },
        },
        "roots": {
            "type": "array",
            "minItems": 0,
            "maxItems": 6,
            "items": {
                "type": "object",
                "required": ["part", "type", "meaning"],
                "properties": {
                    "part": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": ["prefix", "root", "suffix", "other"],
                    },
                    "meaning": {"type": "string"},
                },
            },
        },
        "etymology": {"type": "string"},
        "mnemonic": {
            "type": "string",
            "minLength": 2,
            "maxLength": 120,
        },
        "related": {
            "type": "array",
            "minItems": 0,
            "maxItems": 6,
            "items": {
                "type": "object",
                "required": ["word", "cn"],
                "properties": {
                    "word": {"type": "string"},
                    "cn": {"type": "string"},
                },
            },
        },
    },
}

SENTENCE_GRAMMAR_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "sentence",
        "translation",
        "structure",
        "grammar_points",
        "key_words",
        "difficulty",
    ],
    "properties": {
        "sentence": {"type": "string"},
        "translation": {"type": "string", "minLength": 1},
        "structure": {
            "type": "array",
            "minItems": 1,
            "maxItems": 12,
            "items": {
                "type": "object",
                "required": ["text", "role", "explain"],
                "properties": {
                    "text": {"type": "string"},
                    "role": {"type": "string"},
                    "explain": {"type": "string"},
                },
            },
        },
        "grammar_points": {
            "type": "array",
            "minItems": 0,
            "maxItems": 6,
            "items": {
                "type": "object",
                "required": ["name", "explain"],
                "properties": {
                    "name": {"type": "string"},
                    "explain": {"type": "string"},
                },
            },
        },
        "key_words": {
            "type": "array",
            "minItems": 0,
            "maxItems": 10,
            "items": {
                "type": "object",
                "required": ["word", "pos", "cn", "note"],
                "properties": {
                    "word": {"type": "string"},
                    "pos": {"type": "string"},
                    "cn": {"type": "string"},
                    "note": {"type": "string"},
                },
            },
        },
        "difficulty": {
            "type": "string",
            "enum": ["easy", "medium", "hard"],
        },
    },
}

WORD_QUIZ_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["questions"],
    "properties": {
        "questions": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": [
                    "type",
                    "word",
                    "stem",
                    "options",
                    "answer",
                    "explain",
                ],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["cloze", "choice", "en2zh"],
                    },
                    "word": {"type": "string", "minLength": 1},
                    "stem": {"type": "string", "minLength": 1},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "answer": {"type": "string", "minLength": 1},
                    "explain": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}

SCHEMAS: dict[str, dict[str, Any]] = {
    "word_mnemonic": WORD_MNEMONIC_SCHEMA,
    "sentence_grammar": SENTENCE_GRAMMAR_SCHEMA,
    "word_quiz": WORD_QUIZ_SCHEMA,
}

_VALIDATORS: dict[str, Draft202012Validator] = {
    k: Draft202012Validator(schema) for k, schema in SCHEMAS.items()
}


def validate(kind: str, obj: Any, input_data: dict[str, Any] | None = None) -> list[str]:
    validator = _VALIDATORS.get(kind)
    if validator is None:
        return [f"Unknown kind: {kind}"]
    errors = [err.message for err in validator.iter_errors(obj)]
    if errors:
        return errors

    if kind == "word_quiz" and isinstance(obj, dict):
        questions = obj.get("questions")
        if isinstance(questions, list):
            for i, q in enumerate(questions):
                if not isinstance(q, dict):
                    continue
                q_type = q.get("type")
                options = q.get("options")
                answer = q.get("answer")
                if q_type == "choice":
                    if not isinstance(options, list) or len(options) != 4:
                        errors.append(f"第 {i + 1} 题 choice 题型必须包含 4 个选项")
                    elif answer not in options:
                        errors.append(f"第 {i + 1} 题 choice 题型的 answer '{answer}' 必须在 options 中")
                elif q_type == "cloze":
                    word = str(q.get("word", "")).strip().lower()
                    stem = str(q.get("stem", "")).lower()
                    if word and re.search(r"\b" + re.escape(word) + r"\b", stem):
                        errors.append(f"第 {i + 1} 题 cloze 题干不得直接包含答案原词")

            if input_data and "words" in input_data:
                raw_words = input_data["words"]
                input_word_set: set[str] = set()
                if isinstance(raw_words, list):
                    for item in raw_words:
                        if isinstance(item, dict):
                            w_str = str(item.get("word", "")).strip().lower()
                        else:
                            w_str = str(item).strip().lower()
                        if w_str:
                            input_word_set.add(w_str)

                quiz_word_set = {
                    str(q.get("word", "")).strip().lower()
                    for q in questions
                    if isinstance(q, dict) and q.get("word")
                }
                if input_word_set and len(questions) > 2 * len(input_word_set):
                    errors.append(f"题目总数 {len(questions)} 超过输入词数的 2 倍")
                missing = [w for w in sorted(input_word_set) if w not in quiz_word_set]
                if missing:
                    errors.append(f"每个输入词至少出现在一题中，缺失单词: {', '.join(missing)}")

    return errors
