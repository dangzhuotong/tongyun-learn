import { describe, it, expect } from 'vitest'
import {
  PRACTICE_WORD_CACHE,
  PRACTICE_ARTICLE_CACHE,
  LEGACY_PRACTICE_WORD_CACHE_VERSION,
  PRACTICE_WORD_GROUP_SIZE,
  resolveLegacyPracticeWordCursor,
  checkAndUpgradePracticeWordCache,
} from './cache'
import { WordPracticeMode, WordPracticeStage, WordPracticeType } from '../types/enum'

describe('cache utilities', () => {
  describe('constants', () => {
    it('defines expected cache keys and versions', () => {
      expect(PRACTICE_WORD_CACHE).toEqual({ key: 'PracticeSaveWord', version: 2 })
      expect(PRACTICE_ARTICLE_CACHE).toEqual({ key: 'PracticeSaveArticle', version: 1 })
      expect(LEGACY_PRACTICE_WORD_CACHE_VERSION).toBe(1)
      expect(PRACTICE_WORD_GROUP_SIZE).toBe(7)
    })
  })

  describe('resolveLegacyPracticeWordCursor', () => {
    it('resolves cursor for FollowWriteNewWord stage', () => {
      const cursor = resolveLegacyPracticeWordCursor(
        WordPracticeMode.System,
        WordPracticeStage.FollowWriteNewWord
      )
      expect(cursor).toEqual({
        nodeIndex: 0,
        stepIndex: 0,
        inWrongWordClear: false,
        loop: null,
        endActionIndex: null,
      })
    })

    it('sets stepIndex correctly in System mode for Listen and Dictation stages', () => {
      const listenCursor = resolveLegacyPracticeWordCursor(
        WordPracticeMode.System,
        WordPracticeStage.ListenNewWord
      )
      expect(listenCursor.stepIndex).toBe(1)

      const dictationCursor = resolveLegacyPracticeWordCursor(
        WordPracticeMode.System,
        WordPracticeStage.DictationNewWord
      )
      expect(dictationCursor.stepIndex).toBe(2)
    })

    it('sets nodeIndex to 1 for Review stages in System mode', () => {
      const reviewCursor = resolveLegacyPracticeWordCursor(
        WordPracticeMode.System,
        WordPracticeStage.IdentifyReview
      )
      expect(reviewCursor.nodeIndex).toBe(1)
    })

    it('handles wrong-word typing flags', () => {
      const cursor = resolveLegacyPracticeWordCursor(
        WordPracticeMode.System,
        WordPracticeStage.FollowWriteNewWord,
        { isTypingWrongWord: true }
      )
      expect(cursor.inWrongWordClear).toBe(true)
      expect(cursor.endActionIndex).toBe(0)
    })

    it('computes grouped loop windows for Spell practice mode', () => {
      const cursor = resolveLegacyPracticeWordCursor(
        WordPracticeMode.System,
        WordPracticeStage.FollowWriteNewWord,
        {
          practiceType: WordPracticeType.Spell,
          index: 8,
          wordsLength: 20,
        }
      )
      expect(cursor.loop).toEqual({
        startIndex: 7,
        endIndex: 13,
        subStepIndex: 0,
      })
    })
  })

  describe('checkAndUpgradePracticeWordCache', () => {
    const context = {
      wordPracticeMode: WordPracticeMode.System,
      wordPracticeType: WordPracticeType.Spell,
    }

    it('returns v2 cache directly without modification', () => {
      const raw = {
        version: 2,
        updated_at: '2026-03-01T00:00:00Z',
        val: { taskWordsStr: { new: ['apple'], review: [] } },
      }
      const result = checkAndUpgradePracticeWordCache(raw as any, context)
      expect(result.version).toBe(2)
      expect(result.updated_at).toBe('2026-03-01T00:00:00Z')
      expect(result.val).toEqual(raw.val)
    })

    it('throws error on unsupported legacy version', () => {
      const raw = { version: 99, val: {} }
      expect(() => checkAndUpgradePracticeWordCache(raw, context)).toThrow(
        'UNSUPPORTED_PRACTICE_CACHE_VERSION:99'
      )
    })

    it('upgrades v1 cache to v2 structure', () => {
      const v1Data = {
        version: 1,
        updated_at: '2026-01-01T00:00:00Z',
        val: {
          taskWordsStr: {
            new: ['persevere', 'diligent'],
            review: [],
          },
        },
      }
      const result = checkAndUpgradePracticeWordCache(v1Data, context)
      expect(result.version).toBe(2)
      expect(result.updated_at).toBe('2026-01-01T00:00:00Z')
      expect(result.val?.taskWordsStr).toEqual({
        new: ['persevere', 'diligent'],
        review: [],
      })
    })
  })
})
