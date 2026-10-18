import { describe, it, expect } from 'vitest'
import {
  joinUrl,
  LearnError,
  pickWrongWordsForQuiz,
  gradeQuizAnswer,
  getLearnConfig,
  isLearnConfigured,
  saveLearnConfig,
  clearLearnConfig,
} from './learn-client'

describe('learn-client utilities', () => {
  describe('joinUrl', () => {
    it('joins base and relative paths cleanly without duplicate slashes', () => {
      expect(joinUrl('/learn/api/', 'v1/health')).toBe('/learn/api/v1/health')
      expect(joinUrl('/learn/api', '/v1/health')).toBe('/learn/api/v1/health')
      expect(joinUrl('/learn/api///', '///v1/health')).toBe('/learn/api/v1/health')
    })

    it('handles full origin URLs correctly', () => {
      expect(joinUrl('https://example.com/learn/', 'v1/health')).toBe('https://example.com/learn/v1/health')
      expect(joinUrl('http://127.0.0.1:8031', 'v1/ai/quiz')).toBe('http://127.0.0.1:8031/v1/ai/quiz')
    })

    it('returns root-prefixed path when base is empty', () => {
      expect(joinUrl('', 'v1/health')).toBe('/v1/health')
      expect(joinUrl('', '/v1/health')).toBe('/v1/health')
    })
  })

  describe('LearnError', () => {
    it('constructs an error with code, message, and status', () => {
      const err = new LearnError('bad_token', '令牌无效', 401)
      expect(err).toBeInstanceOf(Error)
      expect(err.name).toBe('LearnError')
      expect(err.code).toBe('bad_token')
      expect(err.message).toBe('令牌无效')
      expect(err.status).toBe(401)
    })

    it('defaults status to 0 when omitted', () => {
      const err = new LearnError('timeout', '请求超时')
      expect(err.status).toBe(0)
    })
  })

  describe('pickWrongWordsForQuiz', () => {
    it('extracts word and first trans cn', () => {
      const words = [
        { word: 'persevere', trans: [{ cn: '坚持' }] },
        { word: 'diligent', trans: [{ cn: '勤奋的' }, { cn: '用功的' }] },
      ]
      const result = pickWrongWordsForQuiz(words)
      expect(result).toEqual([
        { word: 'persevere', cn: '坚持' },
        { word: 'diligent', cn: '勤奋的' },
      ])
    })

    it('filters empty words, non-alphabet words, and words over 64 chars', () => {
      const words = [
        { word: '   ' },
        { word: '12345' },
        { word: '中文单词' },
        { word: 'a'.repeat(65) },
        { word: 'valid' },
      ]
      const result = pickWrongWordsForQuiz(words)
      expect(result).toEqual([{ word: 'valid' }])
    })

    it('deduplicates case-insensitively keeping the first instance', () => {
      const words = [
        { word: 'Apple', trans: [{ cn: '苹果' }] },
        { word: 'apple', trans: [{ cn: '红富士' }] },
      ]
      const result = pickWrongWordsForQuiz(words)
      expect(result).toHaveLength(1)
      expect(result[0]).toEqual({ word: 'Apple', cn: '苹果' })
    })

    it('truncates cn to 100 characters', () => {
      const longCn = '字'.repeat(150)
      const words = [{ word: 'test', trans: [{ cn: longCn }] }]
      const result = pickWrongWordsForQuiz(words)
      expect(result[0].cn).toHaveLength(100)
    })

    it('respects limit parameter up to max 20', () => {
      const words = Array.from({ length: 30 }, (_, i) => ({ word: `word${i}` }))
      expect(pickWrongWordsForQuiz(words, 5)).toHaveLength(5)
      expect(pickWrongWordsForQuiz(words, 25)).toHaveLength(20)
    })
  })

  describe('gradeQuizAnswer', () => {
    it('returns false for empty input or empty answer', () => {
      expect(gradeQuizAnswer('', 'answer')).toBe(false)
      expect(gradeQuizAnswer('answer', '')).toBe(false)
      expect(gradeQuizAnswer('   ', '   ')).toBe(false)
    })

    it('matches case-insensitively with trim', () => {
      expect(gradeQuizAnswer('Apple', 'apple')).toBe(true)
      expect(gradeQuizAnswer('  apple  ', 'APPLE')).toBe(true)
      expect(gradeQuizAnswer('banana', 'apple')).toBe(false)
    })

    it('tolerates trailing punctuation on the expected answer', () => {
      expect(gradeQuizAnswer('apple', 'apple.')).toBe(true)
      expect(gradeQuizAnswer('apple', 'apple! ')).toBe(true)
      expect(gradeQuizAnswer('apple', 'apple?')).toBe(true)
      expect(gradeQuizAnswer('苹果', '苹果。')).toBe(true)
    })

    it('accepts any matched definition from multi-definition answers', () => {
      expect(gradeQuizAnswer('放弃', '放弃；抛弃')).toBe(true)
      expect(gradeQuizAnswer('抛弃', '放弃, 抛弃')).toBe(true)
      expect(gradeQuizAnswer('丢弃', '放弃 / 抛弃 / 丢弃')).toBe(true)
      expect(gradeQuizAnswer('坚持', '放弃；抛弃')).toBe(false)
    })
  })

  describe('configuration helpers in node environment', () => {
    it('returns default config when window is undefined', () => {
      expect(getLearnConfig()).toEqual({ url: '/learn/api/', token: '' })
      expect(isLearnConfigured()).toBe(false)
    })

    it('safely handles save and clear when window is undefined', () => {
      expect(() => saveLearnConfig({ url: '/custom/' })).not.toThrow()
      expect(() => clearLearnConfig()).not.toThrow()
    })
  })
})
