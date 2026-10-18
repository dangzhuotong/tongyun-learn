// tongyun: 学科敲字练习判分。code 题（java-0003/0015/0017、ai-0019、web/tools 等）判对忽略空白；支持 choice 选项与 oral/project 自评题型。
import type { QuestionItem } from './types'

export const CODE_QUESTION_IDS = new Set(['java-0003', 'java-0015', 'java-0017', 'ai-0019'])

export function isCodeQuestion(item: { type?: string; id?: string }): boolean {
  if (item.type === 'code') return true
  if (item.id && CODE_QUESTION_IDS.has(item.id)) return true
  return false
}

export function foldQuotes(input: string): string {
  return (input || '').replace(/[’‘]/g, "'").replace(/[“”]/g, '"')
}

export function stripWhitespace(input: string): string {
  return foldQuotes(input).replace(/\s+/g, '')
}

export function normalizeStandard(input: string): string {
  return foldQuotes(input).trim().toLowerCase()
}

/**
 * 答案判定：
 * 1. 忽略空白字符（对 code 题型生效，包含 java-0003/0015/0017、ai-0019 等）。
 * 2. choice 选择题支持全文字符比对、大小写字母编号（A/B/C/D）与数字编号（1/2/3/4）。
 * 3. oral / project 自评题支持「自评完成」「完成」「已完成」「通过」等标记判定。
 * 4. 普通题去除首尾空白，不区分大小写，且兼容中文全角半角标点/引号与 accept 候选项。
 */
export function gradeAnswer(typed: string, item: QuestionItem): boolean {
  const t = (typed || '').trim()
  if (!t) return false

  // 1. 口述/项目自评题支持自评完成词
  if (item.type === 'oral' || item.type === 'project' || item.grading === 'self') {
    const selfTokens = new Set(['自评完成', '完成', '已完成', '通过', 'pass', 'done', 'ok', 'yes'])
    if (selfTokens.has(t.toLowerCase()) || selfTokens.has(t)) return true
  }

  // 2. 选择题支持字母索引 A/B/C/D 或数字 1/2/3/4
  if (item.type === 'choice' && Array.isArray(item.options)) {
    const numIdx = parseInt(t, 10)
    if (!isNaN(numIdx) && numIdx >= 1 && numIdx <= item.options.length) {
      if (item.options[numIdx - 1] === item.answer) return true
    }
    if (t.length === 1) {
      const letterIdx = t.toUpperCase().charCodeAt(0) - 65
      if (letterIdx >= 0 && letterIdx < item.options.length) {
        if (item.options[letterIdx] === item.answer) return true
      }
    }
  }

  const candidates = [item.answer, ...(item.accept || [])].filter(Boolean)
  const isCode = isCodeQuestion(item)

  if (isCode) {
    const strippedTyped = stripWhitespace(t)
    const strippedTypedNoSemi = strippedTyped.replace(/;+$/, '')

    for (const cand of candidates) {
      const strippedCand = stripWhitespace(cand)
      if (strippedCand === strippedTyped) return true
      if (strippedCand.replace(/;+$/, '') === strippedTypedNoSemi) return true
    }
    return false
  }

  const normTyped = normalizeStandard(t)
  const rawTrimmed = foldQuotes(t).trim()

  for (const cand of candidates) {
    if (foldQuotes(cand).trim() === rawTrimmed) return true
    if (normalizeStandard(cand) === normTyped) return true
  }

  return false
}
