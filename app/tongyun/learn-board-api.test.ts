import { describe, it, expect } from 'vitest'
import {
  POINT_STATES,
  normalizePointState,
  stateLabel,
  stateColor,
  formatRetention,
  fetchSubjects,
  fetchNext,
  fetchReviewDue,
  fetchProgress,
  fetchOpenBlockers,
} from './learn-board-api'

describe('learn-board-api utilities', () => {
  describe('POINT_STATES metadata', () => {
    it('defines standard learning point states without locked (all points openable)', () => {
      expect(POINT_STATES).toHaveLength(5)
      const keys = POINT_STATES.map(s => s.key)
      expect(keys).toEqual(['available', 'learning', 'learned', 'mastered', 'rusty'])
      expect(keys).not.toContain('locked')
    })
  })

  describe('normalizePointState', () => {
    it('normalizes null, undefined, or locked states to available', () => {
      expect(normalizePointState(null)).toBe('available')
      expect(normalizePointState(undefined)).toBe('available')
      expect(normalizePointState('')).toBe('available')
      expect(normalizePointState('locked')).toBe('available')
    })

    it('preserves other valid states', () => {
      expect(normalizePointState('available')).toBe('available')
      expect(normalizePointState('learning')).toBe('learning')
      expect(normalizePointState('mastered')).toBe('mastered')
    })
  })

  describe('stateLabel', () => {
    it('maps known state keys to Chinese labels and maps locked to 可学', () => {
      expect(stateLabel('locked')).toBe('可学')
      expect(stateLabel('available')).toBe('可学')
      expect(stateLabel('learning')).toBe('学习中')
      expect(stateLabel('learned')).toBe('学过')
      expect(stateLabel('mastered')).toBe('掌握')
      expect(stateLabel('rusty')).toBe('生疏')
    })

    it('falls back to "未知" for unknown, null, or undefined states', () => {
      expect(stateLabel(null)).toBe('未知')
      expect(stateLabel(undefined)).toBe('未知')
      expect(stateLabel('')).toBe('未知')
      expect(stateLabel('non_existent')).toBe('未知')
    })
  })

  describe('stateColor', () => {
    it('maps known state keys to hexadecimal colors and maps locked to available color', () => {
      expect(stateColor('locked')).toBe('#3b82f6')
      expect(stateColor('available')).toBe('#3b82f6')
      expect(stateColor('learning')).toBe('#f59e0b')
      expect(stateColor('learned')).toBe('#14b8a6')
      expect(stateColor('mastered')).toBe('#22c55e')
      expect(stateColor('rusty')).toBe('#ef4444')
    })

    it('falls back to default color for unknown, null, or undefined states', () => {
      expect(stateColor(null)).toBe('#9ca3af')
      expect(stateColor(undefined)).toBe('#9ca3af')
      expect(stateColor('')).toBe('#9ca3af')
      expect(stateColor('non_existent')).toBe('#9ca3af')
    })
  })

  describe('formatRetention', () => {
    it('returns "—" for null, undefined, NaN, or non-number values', () => {
      expect(formatRetention(null)).toBe('—')
      expect(formatRetention(undefined)).toBe('—')
      expect(formatRetention(NaN)).toBe('—')
      expect(formatRetention('0.5' as any)).toBe('—')
    })

    it('formats numeric ratios as percentage strings without trailing .0', () => {
      expect(formatRetention(0)).toBe('0%')
      expect(formatRetention(1)).toBe('100%')
      expect(formatRetention(0.5)).toBe('50%')
      expect(formatRetention(0.85)).toBe('85%')
      expect(formatRetention(0.8567)).toBe('85.7%')
    })
  })

  describe('board API helpers with unconfigured token', () => {
    it('returns no_token error without initiating network request when token is empty', async () => {
      const subjectsResult = await fetchSubjects()
      expect(subjectsResult).toEqual({ ok: false, kind: 'no_token', status: 0 })

      const nextResult = await fetchNext()
      expect(nextResult).toEqual({ ok: false, kind: 'no_token', status: 0 })

      const reviewResult = await fetchReviewDue()
      expect(reviewResult).toEqual({ ok: false, kind: 'no_token', status: 0 })

      const progressResult = await fetchProgress()
      expect(progressResult).toEqual({ ok: false, kind: 'no_token', status: 0 })

      const blockersResult = await fetchOpenBlockers()
      expect(blockersResult).toEqual({ ok: false, kind: 'no_token', status: 0 })
    })
  })
})
