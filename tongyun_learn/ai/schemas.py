from typing import Any

from jsonschema import Draft202012Validator

KINDS: dict[str, dict[str, str]] = {
    "word_mnemonic": {"prompt_ver": "w1"},
    "sentence_grammar": {"prompt_ver": "s1"},
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

SCHEMAS: dict[str, dict[str, Any]] = {
    "word_mnemonic": WORD_MNEMONIC_SCHEMA,
    "sentence_grammar": SENTENCE_GRAMMAR_SCHEMA,
}

_VALIDATORS: dict[str, Draft202012Validator] = {
    k: Draft202012Validator(schema) for k, schema in SCHEMAS.items()
}


def validate(kind: str, obj: Any) -> list[str]:
    validator = _VALIDATORS.get(kind)
    if validator is None:
        return [f"Unknown kind: {kind}"]
    return [err.message for err in validator.iter_errors(obj)]
