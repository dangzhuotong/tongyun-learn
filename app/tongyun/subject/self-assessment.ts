// tongyun: oral / project 的自评三档 → 复习间隔。
// 不会：1 天后再来；半会：3 天；会：走正常间隔（由调用方给出，如 1/3/7/14/30）。

import type { SelfAssessment } from './types'

export const DAY = 24 * 3600 * 1000
export const SELF_FAIL_DAYS = 1
export const SELF_PARTIAL_DAYS = 3

export const SELF_LABELS: Record<SelfAssessment, string> = {
  self_ok: '会',
  self_partial: '半会',
  self_fail: '不会',
}

export const SELF_OPTIONS: SelfAssessment[] = ['self_ok', 'self_partial', 'self_fail']

export function isSelfAssessment(v: unknown): v is SelfAssessment {
  return v === 'self_ok' || v === 'self_partial' || v === 'self_fail'
}

/** 自评驱动的间隔天数。normalDays 是「会」时的正常间隔。 */
export function selfIntervalDays(assessment: SelfAssessment, normalDays: number): number {
  if (assessment === 'self_fail') return SELF_FAIL_DAYS
  if (assessment === 'self_partial') return SELF_PARTIAL_DAYS
  return normalizeNormal(normalDays)
}

function normalizeNormal(normalDays: number): number {
  return Number.isFinite(normalDays) && normalDays > 0 ? normalDays : SELF_FAIL_DAYS
}

/** 自评后的下次到期时间戳。 */
export function selfNextDue(
  assessment: SelfAssessment,
  normalDays: number,
  now: number = Date.now()
): number {
  return now + selfIntervalDays(assessment, normalDays) * DAY
}

export interface SelfScheduleState {
  /** 正常排课档位（0 起），「会」时前进一档 */
  box: number
  /** 正常间隔表，如 [1, 3, 7, 14, 30] */
  intervals: number[]
  now: number
}

export interface SelfScheduleResult {
  box: number
  due: number
  assessment: SelfAssessment
}

/**
 * 把自评结果落到排课状态：
 * - 会：正常前进一档，按间隔表排期；
 * - 半会：3 天，档位不前进；
 * - 不会：1 天，档位重置到 0。
 */
export function applySelfAssessment(
  assessment: SelfAssessment,
  state: SelfScheduleState
): SelfScheduleResult {
  const { intervals, now } = state
  if (assessment === 'self_ok') {
    const box = Math.max(0, Math.min(intervals.length - 1, state.box + 1))
    return { box, due: now + intervals[box]! * DAY, assessment }
  }
  if (assessment === 'self_partial') {
    return { box: Math.max(0, state.box), due: now + SELF_PARTIAL_DAYS * DAY, assessment }
  }
  return { box: 0, due: now + SELF_FAIL_DAYS * DAY, assessment }
}
