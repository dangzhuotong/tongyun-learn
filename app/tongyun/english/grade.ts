// tongyun: 敲词 / 敲句判分。松紧来自设置，过关规则不在这里排课。

import type { EnglishPrefs } from './prefs'
import { DEFAULT_ENGLISH_PREFS } from './prefs'
import type { PracticeStage } from './types'

export type LetterMark = 'ok' | 'bad' | 'left' | 'next'

export interface GradePrefs {
  strictCase: boolean
  loosePunctuation: boolean
}

export function gradePrefsOf(prefs: EnglishPrefs = DEFAULT_ENGLISH_PREFS): GradePrefs {
  return {
    strictCase: prefs.strictCase,
    loosePunctuation: prefs.loosePunctuation,
  }
}

function foldQuotes(input: string): string {
  return input.replace(/[’‘]/g, "'").replace(/[“”]/g, '"')
}

export function canonicalize(input: string, stage: PracticeStage, prefs: GradePrefs): string {
  let s = foldQuotes(input || '')
    .trim()
    .replace(/\s+/g, ' ')
  if (stage === 'B' && prefs.loosePunctuation) {
    s = s.replace(/[.,!?;:，。！？；：、…]/g, '')
    s = s.replace(/"/g, '')
    s = s.replace(/\s+/g, ' ').trim()
  }
  if (!prefs.strictCase) s = s.toLowerCase()
  return s
}

export function gradeTyped(typed: string, expected: string, stage: PracticeStage, prefs: GradePrefs): boolean {
  const a = canonicalize(typed, stage, prefs)
  const b = canonicalize(expected, stage, prefs)
  if (!a || !b) return false
  return a === b
}

function sameChar(expected: string, typed: string, strictCase: boolean): boolean {
  const a = foldQuotes(expected)
  const b = foldQuotes(typed)
  if (strictCase) return a === b
  return a.toLowerCase() === b.toLowerCase()
}

/** 大词上色：按目标词的字符对齐，多敲的部分留给输入条 */
export function markLetters(expected: string, typed: string, prefs: GradePrefs): LetterMark[] {
  const chars = [...expected]
  const typedChars = [...typed]
  let prefixOk = true
  return chars.map((ch, i) => {
    if (!prefixOk) return 'left'
    if (i >= typedChars.length) return i === typedChars.length ? 'next' : 'left'
    if (sameChar(ch, typedChars[i], prefs.strictCase)) return 'ok'
    prefixOk = false
    return 'bad'
  })
}
