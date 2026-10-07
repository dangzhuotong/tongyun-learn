from typing import Any

WORD_MNEMONIC_SYSTEM_PROMPT = (
    "你是英语词汇老师，帮中国学习者记单词。只输出一个 JSON 对象，不要 markdown、不要解释。"
    "字段：word(原词)、phonetic(美式音标，形如 /əˈbændən/)、meanings(常用词性与中文义，1-6 条，{pos,cn})、"
    "examples(2-3 条地道、简短、贴近日常或技术场景的例句，{en,zh})、"
    "roots(词根词缀拆分，{part,type:prefix|root|suffix|other,meaning}；拆不了就给空数组，绝不硬编)、"
    "etymology(一两句中文词源故事；不确定就写“词源不详”)、"
    "mnemonic(一句好记的中文口诀/联想，≤40 字，结合拆分或谐音，不低俗)、"
    "related(同根词或易混词 0-6 个，{word,cn})。"
)

SENTENCE_GRAMMAR_SYSTEM_PROMPT = (
    "你是英语语法老师，给中国学习者讲解一个英文句子。只输出一个 JSON 对象，不要 markdown、不要解释。"
    "字段：sentence(原句)、translation(自然通顺的中文翻译)、"
    "structure(按顺序拆出句子成分，{text:原文片段, role:成分名如 "
    "主语/谓语/宾语/表语/定语从句/状语从句/非谓语/插入语, explain:一句中文说明}，1-12 条)、"
    "grammar_points(本句涉及的重点语法 0-6 条，{name,explain}，explain 要具体到本句)、"
    "key_words(重点词/短语 0-10 个，{word,pos,cn,note}，note 可写搭配或易错点，可为空串)、"
    "difficulty(easy|medium|hard)。"
)


def build_messages(kind: str, input_data: dict[str, Any]) -> list[dict[str, str]]:
    if kind == "word_mnemonic":
        word = input_data.get("word", "")
        context = input_data.get("context", "")
        user_content = f"单词：{word}"
        if context:
            user_content += f"\n参考释义：{context}"
        return [
            {"role": "system", "content": WORD_MNEMONIC_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
    elif kind == "sentence_grammar":
        sentence = input_data.get("sentence", "")
        context = input_data.get("context", "")
        user_content = f"句子：{sentence}"
        if context:
            user_content += f"\n上下文（仅供理解，不要讲解它）：{context}"
        return [
            {"role": "system", "content": SENTENCE_GRAMMAR_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
    else:
        raise ValueError(f"Unknown kind: {kind}")


def repair_message(errors: list[str]) -> dict[str, str]:
    err_str = "；".join(errors[:5]) if errors else ""
    return {
        "role": "user",
        "content": f"你上一次的输出不符合要求：{err_str}。请只输出修正后的完整 JSON 对象。",
    }
