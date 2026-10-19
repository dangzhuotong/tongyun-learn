// tongyun: 学科卡片判分。
// - code 题只看 type === 'code' 来识别，不维护卡片 id 白名单；
// - choice 自动判（answer 必须在 options 里）；
// - oral / project 返回 'self'，交给自评。

import type { Card, ItemType } from './types'

export type GradeResult = 'correct' | 'wrong' | 'self'

export interface GradeOptions {
  caseSensitive?: boolean
}

function collapse(s: string): string {
  return (s ?? '').replace(/\s+/g, ' ').trim()
}

/** 是否是 code 卡：只看 type，不看 id 列表 */
export function isCodeQuestion(card: Pick<Card, 'type'>): boolean {
  return card.type === 'code'
}

export function isSelfQuestion(type: ItemType): boolean {
  return type === 'oral' || type === 'project'
}

function equal(a: string, b: string, caseSensitive: boolean): boolean {
  const x = collapse(a)
  const y = collapse(b)
  return caseSensitive ? x === y : x.toLowerCase() === y.toLowerCase()
}

function stripTrailingSemicolons(s: string): string {
  return collapse(s).replace(/[;，；\s]+$/g, '')
}

function codeEqual(a: string, b: string, caseSensitive: boolean): boolean {
  const x = stripTrailingSemicolons(a)
  const y = stripTrailingSemicolons(b)
  return caseSensitive ? x === y : x.toLowerCase() === y.toLowerCase()
}

/** choice：选中项与 answer 完全一致即对。 */
export function gradeChoice(card: Pick<Card, 'answer'>, chosen: string): boolean {
  return typeof chosen === 'string' && chosen === card.answer
}

/** code：忽略多余空白与行尾分号。 */
export function gradeCode(
  card: Pick<Card, 'answer' | 'accept'>,
  typed: string,
  options: GradeOptions = {}
): boolean {
  const caseSensitive = options.caseSensitive ?? false
  if (codeEqual(typed, card.answer, caseSensitive)) return true
  return (card.accept ?? []).some(a => codeEqual(typed, a, caseSensitive))
}

/** 文本题：answer 或 accept 命中即对；code 题同此，只是识别方式不同。 */
export function gradeText(
  card: Pick<Card, 'answer' | 'accept'>,
  typed: string,
  options: GradeOptions = {}
): boolean {
  const caseSensitive = options.caseSensitive ?? false
  if (equal(typed, card.answer, caseSensitive)) return true
  return (card.accept ?? []).some(a => equal(typed, a, caseSensitive))
}

export function gradeCard(card: Card, response: string, options: GradeOptions = {}): GradeResult {
  if (card.type === 'choice') return gradeChoice(card, response) ? 'correct' : 'wrong'
  if (isSelfQuestion(card.type)) return 'self'
  // code 由 type === 'code' 决定，不看 id 列表
  if (isCodeQuestion(card)) return gradeCode(card, response, options) ? 'correct' : 'wrong'
  return gradeText(card, response, options) ? 'correct' : 'wrong'
}
