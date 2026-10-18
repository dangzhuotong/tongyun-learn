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

WORD_QUIZ_SYSTEM_PROMPT = (
    "你是英语教学专家，为中国学习者根据错词列表生成复习测试卷。只输出一个 JSON 对象，不要 markdown、不要解释。"
    "JSON 结构：{\"questions\":[{\"type\":\"cloze\"|\"choice\"|\"en2zh\",\"word\":\"原词\","
    "\"stem\":\"题干\",\"options\":[\"A\",\"B\",\"C\",\"D\"],\"answer\":\"标准答案\",\"explain\":\"一句中文解析\"}]}。"
    "要求："
    "1. 题型 type 仅限 cloze（完形填空）、choice（单选题）、en2zh（英译中）。"
    "2. choice 题型的 options 必须包含 4 个选项，且 answer 必须是其中一个选项；"
    "cloze 和 en2zh 题型的 options 必须给空数组 []。"
    "3. 题干 stem 不得直接包含 cloze 的答案原词（可用下划线 ___ 替代）。"
    "4. 每个词至少出 1 题，总题数不超过输入词数的 2 倍。"
    "5. explain 必须是一句简短的中文解析。"
)

WORD_DECK_SYSTEM_PROMPT = (
    "你是英语教学专家，为学习者根据指定场景生成一批实用英语单词卡。只输出一个 JSON 对象，不要 markdown、不要解释。"
    "JSON 结构：{\"words\":[{\"word\":\"原词\",\"phonetic\":\"音标\",\"cn\":\"中文释义\","
    "\"example\":\"英文例句\",\"example_cn\":\"例句中文翻译\"}]}。"
    "要求："
    "1. words 数量在 1 到 指定数量 n 之间，围绕指定场景挑选高频、地道词汇。"
    "2. word 必须包含英文字母且长度 ≤64；cn 必须非空且简洁明了。"
    "3. phonetic（音标）、example（英文例句）、example_cn（例句中文）尽量提供。"
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
    elif kind == "word_quiz":
        words_list = input_data.get("words", [])
        lines = []
        for item in words_list:
            if isinstance(item, dict):
                w = item.get("word", "")
                cn = item.get("cn")
                if cn:
                    lines.append(f"- {w}（参考释义：{cn}）")
                else:
                    lines.append(f"- {w}")
            else:
                lines.append(f"- {item}")
        user_content = "请为以下错词生成复习测试卷：\n" + "\n".join(lines)
        return [
            {"role": "system", "content": WORD_QUIZ_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
    elif kind == "word_deck":
        scenario = input_data.get("scenario", "")
        n = input_data.get("n", 20)
        user_content = f"场景：{scenario}\n请生成不超过 {n} 个词汇的词书卡片。"
        return [
            {"role": "system", "content": WORD_DECK_SYSTEM_PROMPT},
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
