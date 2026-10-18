// tongyun: 学科敲字练习判分。code 题（java-0003/0015/0017、ai-0019）判对忽略空白。
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
 * 1. 忽略空白字符（对 code 题型生效，包含 java-0003/0015/0017、ai-0019）。
 * 2. 无论 code 题或普通题，均与 answer 和 accept 数组中的候选项逐一比对。
 * 3. 普通题去除首尾空白，不区分大小写，且兼容中文全角半角标点/引号。
 */
export function gradeAnswer(typed: string, item: QuestionItem): boolean {
  const t = (typed || '').trim()
  if (!t) return false

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
