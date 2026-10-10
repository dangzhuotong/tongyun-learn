import hashlib
import json
import logging
import time
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tongyun_learn.ai.kie import KieClient, KieError, parse_json_text
from tongyun_learn.ai.prompts import build_messages, repair_message
from tongyun_learn.ai.schemas import KINDS, validate
from tongyun_learn.auth import Principal
from tongyun_learn.config import Settings, get_settings
from tongyun_learn.errors import ApiError
from tongyun_learn.limits import bump_ai_calls, check_ai_cap
from tongyun_learn.models import AiCache

logger = logging.getLogger("tongyun_learn.ai.service")


def _log_kie_failure(kind: str, model: str, exc: KieError) -> None:
    # KieError messages are already sanitized (no API key); keep them short.
    logger.warning(
        "ai_explain: KIE call failed kind=%s model=%s code=%s retryable=%s msg=%.200s",
        kind,
        model,
        exc.code,
        exc.retryable,
        exc.message,
    )


def canonical_input(kind: str, input_data: dict[str, Any]) -> str:
    if kind == "word_mnemonic":
        word = str(input_data.get("word", "")).strip()
        context = str(input_data.get("context") or "").strip()
        obj = {"context": context, "word": word}
    elif kind == "sentence_grammar":
        sentence = " ".join(str(input_data.get("sentence", "")).split())
        context = " ".join(str(input_data.get("context") or "").split())
        obj = {"context": context, "sentence": sentence}
    elif kind == "word_quiz":
        seen: set[str] = set()
        words_list: list[dict[str, str]] = []
        for item in input_data.get("words", []):
            if not isinstance(item, dict):
                continue
            w = str(item.get("word", "")).strip()
            c = str(item.get("cn") or "").strip()
            key = w.lower()
            if key not in seen:
                seen.add(key)
                words_list.append({"cn": c, "word": w})
        words_list.sort(key=lambda x: x["word"].lower())
        obj = {"words": words_list}
    else:
        obj = input_data
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def cache_key(kind: str, model: str, prompt_ver: str, input_canonical: str) -> str:
    raw = f"{kind}|{model}|{prompt_ver}|{input_canonical}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_kie_client() -> KieClient:
    settings = get_settings()
    api_key = (
        settings.kie_api_key.get_secret_value()
        if hasattr(settings.kie_api_key, "get_secret_value")
        else str(settings.kie_api_key)
    )
    return KieClient(
        base_url=settings.kie_base_url,
        api_key=api_key,
        timeout_s=settings.ai_timeout_s,
    )


async def explain(
    db: Session,
    principal: Principal,
    kind: str,
    input_data: dict[str, Any],
    client_factory: Any = None,
    client: KieClient | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    if settings is None:
        settings = get_settings()
    if client is None:
        if client_factory is not None:
            client = client_factory() if callable(client_factory) else client_factory
        else:
            client = get_kie_client()

    prompt_ver = KINDS.get(kind, {}).get("prompt_ver", "v1")
    input_canon = canonical_input(kind, input_data)

    models = [settings.ai_model]
    if settings.ai_fallback_model and settings.ai_fallback_model != settings.ai_model:
        models.append(settings.ai_fallback_model)

    # 2. Cache lookup for each model (primary first)
    for model in models:
        ckey = cache_key(kind, model, prompt_ver, input_canon)
        cached_entry = db.query(AiCache).filter(AiCache.cache_key == ckey).first()
        if cached_entry:
            return {
                "kind": kind,
                "model": cached_entry.model,
                "prompt_ver": cached_entry.prompt_ver,
                "cached": True,
                "content": cached_entry.content,
            }

    # 3. Check KIE API key
    api_key_str = (
        settings.kie_api_key.get_secret_value()
        if hasattr(settings.kie_api_key, "get_secret_value")
        else str(settings.kie_api_key)
    )
    if not api_key_str.strip():
        raise ApiError(503, "ai_not_configured", "AI 服务未配置")

    # 4. Check daily AI cap & bump AI calls once
    check_ai_cap(db, principal.name, settings)
    bump_ai_calls(db, principal.name, settings)

    # 5. KIE calling loop with total budget tracking
    deadline = time.monotonic() + settings.ai_total_budget_s
    attempts_count = 0
    total_tokens_in = 0
    total_tokens_out = 0
    total_credits: float = 0.0
    last_failure_was_validation = False
    succeeded_model: str | None = None
    succeeded_content: dict[str, Any] | None = None

    for model in models:
        messages = build_messages(kind, input_data)

        # First attempt on model
        remaining = deadline - time.monotonic()
        if remaining < 3.0:
            raise ApiError(
                502,
                "ai_unavailable",
                "AI 服务暂时不可用，请稍后重试",
                details={"attempts": attempts_count},
            )

        attempts_count += 1
        call_timeout = min(settings.ai_timeout_s, remaining)
        try:
            res = await client.complete(model, messages, timeout=call_timeout)
            if res.tokens_in:
                total_tokens_in += res.tokens_in
            if res.tokens_out:
                total_tokens_out += res.tokens_out
            if res.credits:
                total_credits += res.credits
        except KieError as exc:
            _log_kie_failure(kind, model, exc)
            last_failure_was_validation = False
            continue

        valid = False
        parsed_obj: dict[str, Any] | None = None
        errors: list[str] = []
        try:
            parsed_obj = parse_json_text(res.text)
            errors = validate(kind, parsed_obj, input_data)
            if not errors:
                valid = True
        except Exception as e:
            errors = [f"JSON parse error: {e}"]

        if valid and parsed_obj is not None:
            succeeded_model = model
            succeeded_content = parsed_obj
            break

        # Attempt failed parse or validation -> retry once on same model
        logger.warning("ai_explain: invalid output kind=%s model=%s errors=%d; retrying", kind, model, len(errors))
        last_failure_was_validation = True
        remaining = deadline - time.monotonic()
        if remaining < 3.0:
            break

        attempts_count += 1
        call_timeout = min(settings.ai_timeout_s, remaining)
        repair_msg = repair_message(errors)
        retry_messages = list(messages) + [
            {"role": "assistant", "content": res.text},
            repair_msg,
        ]

        try:
            res_retry = await client.complete(model, retry_messages, timeout=call_timeout)
            if res_retry.tokens_in:
                total_tokens_in += res_retry.tokens_in
            if res_retry.tokens_out:
                total_tokens_out += res_retry.tokens_out
            if res_retry.credits:
                total_credits += res_retry.credits
        except KieError as exc:
            _log_kie_failure(kind, model, exc)
            last_failure_was_validation = False
            continue

        try:
            parsed_retry = parse_json_text(res_retry.text)
            retry_errors = validate(kind, parsed_retry, input_data)
            if not retry_errors:
                succeeded_model = model
                succeeded_content = parsed_retry
                break
            else:
                logger.warning("ai_explain: invalid output after retry kind=%s model=%s", kind, model)
                last_failure_was_validation = True
        except Exception:
            logger.warning("ai_explain: unparsable output after retry kind=%s model=%s", kind, model)
            last_failure_was_validation = True

    # Check if succeeded
    if succeeded_model is not None and succeeded_content is not None:
        # Force content["word"]/content["sentence"] to requested value if missing
        if kind == "word_mnemonic":
            if not succeeded_content.get("word"):
                succeeded_content["word"] = input_data.get("word")
        elif kind == "sentence_grammar":
            if not succeeded_content.get("sentence"):
                succeeded_content["sentence"] = input_data.get("sentence")

        succ_key = cache_key(kind, succeeded_model, prompt_ver, input_canon)
        cache_row = AiCache(
            cache_key=succ_key,
            kind=kind,
            model=succeeded_model,
            prompt_ver=prompt_ver,
            content=succeeded_content,
            tokens_in=total_tokens_in if total_tokens_in > 0 else None,
            tokens_out=total_tokens_out if total_tokens_out > 0 else None,
        )
        try:
            db.add(cache_row)
            db.commit()
        except IntegrityError:
            db.rollback()

        logger.info(
            "ai_explain: kind=%s model=%s tokens_in=%s tokens_out=%s credits=%s cached=false",
            kind,
            succeeded_model,
            total_tokens_in,
            total_tokens_out,
            total_credits,
        )

        return {
            "kind": kind,
            "model": succeeded_model,
            "prompt_ver": prompt_ver,
            "cached": False,
            "content": succeeded_content,
        }

    # All failed
    logger.warning(
        "ai_explain: all attempts failed kind=%s attempts=%d credits=%s", kind, attempts_count, total_credits
    )
    err_code = "ai_bad_output" if last_failure_was_validation else "ai_unavailable"
    raise ApiError(
        502,
        err_code,
        "AI 服务暂时不可用，请稍后重试",
        details={"attempts": attempts_count},
    )
