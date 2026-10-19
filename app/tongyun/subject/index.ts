// tongyun: 学科敲字练习模块导出
export * from './types'
export * from './bank'
export * from './parse'
export * from './registry'
export * from './grade'
export * from './self-assessment'
export {
  useActiveSubject,
  __resetActiveSubject,
} from './active-subject'
export * from './stats'
export * from './session'
export {
  getActiveSubject,
  setActiveSubject,
  isBankSubject,
  type ActiveSubject,
} from './ui-subject'

import { gradeCard, type GradeResult } from './grade'
import type { Card } from './types'

/** 练习层兼容：把 GradeResult 收成 boolean（self 视为未自动判对） */
export function gradeAnswer(typed: string, item: Card): boolean {
  const r: GradeResult = gradeCard(item, typed)
  return r === 'correct'
}
