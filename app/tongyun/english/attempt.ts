// tongyun: 一张卡的敲击。允许一次改对；用了这次修正仍记错，第二次还错就揭晓。

import { gradeTyped, type GradePrefs } from './grade'
import type { PracticeStage } from './types'

export type AttemptPhase = 'editing' | 'hold' | 'done'

export interface AttemptState {
  typed: string
  failures: number
  phase: AttemptPhase
  correct: boolean
  usedCorrection: boolean
  /** 交给教练的错误串：第一次敲错的内容；一次过则是最终文本 */
  eventTyped: string
  hint: string
}

export function freshAttempt(): AttemptState {
  return {
    typed: '',
    failures: 0,
    phase: 'editing',
    correct: false,
    usedCorrection: false,
    eventTyped: '',
    hint: '',
  }
}

export function isResolved(state: AttemptState): boolean {
  return state.phase === 'hold' || state.phase === 'done'
}

export function submitAttempt(
  state: AttemptState,
  expected: string,
  stage: PracticeStage,
  prefs: GradePrefs
): AttemptState {
  const typed = state.typed
  if (!typed.trim()) return state
  const ok = gradeTyped(typed, expected, stage, prefs)
  if (ok && state.failures === 0) {
    return {
      ...state,
      phase: 'done',
      correct: true,
      usedCorrection: false,
      eventTyped: typed.trim(),
      hint: '按空格继续',
    }
  }
  if (ok) {
    return {
      ...state,
      phase: 'hold',
      correct: false,
      usedCorrection: true,
      eventTyped: state.eventTyped || typed.trim(),
      hint: '改对了，这次记入错词。按空格继续',
    }
  }
  const failures = state.failures + 1
  const eventTyped = state.eventTyped || typed.trim()
  if (failures < 2) {
    return {
      ...state,
      failures,
      phase: 'editing',
      eventTyped,
      hint: '再改一次',
    }
  }
  return {
    ...state,
    failures,
    phase: 'hold',
    correct: false,
    usedCorrection: false,
    eventTyped,
    hint: `正确是 ${expected}`,
  }
}

export function attemptCount(state: AttemptState): number {
  if (state.correct || state.usedCorrection) return state.failures + 1
  return state.failures
}
