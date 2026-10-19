import { describe, expect, it } from 'vitest'
import {
  getFirstWrongCharacterIndex,
  getPracticeInputCharacterStates,
  getWholeInputAfterWrongBackspace,
  isPracticeCharacterCorrect,
  isWholePracticeInputComplete,
  isWholePracticeInputCorrect,
  normalizePracticeInputCharacter,
} from './visible-word-typing'

describe('normalizePracticeInputCharacter', () => {
  it('maps shifted full-width punctuation by physical key', () => {
    expect(normalizePracticeInputCharacter({ key: '!', code: 'Digit1', shiftKey: true }, '！')).toBe('！')
    expect(normalizePracticeInputCharacter({ key: '-', code: 'Minus', shiftKey: true }, '—')).toBe('—')
    expect(normalizePracticeInputCharacter({ key: '?', code: 'Slash', shiftKey: true }, '？')).toBe('？')
  })

  it('maps unshifted full-width punctuation by physical key', () => {
    expect(normalizePracticeInputCharacter({ key: '/', code: 'Slash', shiftKey: false }, '、')).toBe('、')
    expect(normalizePracticeInputCharacter({ key: '.', code: 'Period', shiftKey: false }, '。')).toBe('。')
    expect(normalizePracticeInputCharacter({ key: ',', code: 'Comma', shiftKey: false }, '，')).toBe('，')
  })

  it('falls back to the raw key when the target does not match the map', () => {
    expect(normalizePracticeInputCharacter({ key: '!', code: 'Digit1', shiftKey: false }, '！')).toBe('!')
    expect(normalizePracticeInputCharacter({ key: 'a', code: 'KeyA', shiftKey: false }, 'a')).toBe('a')
    expect(normalizePracticeInputCharacter({ key: 'x', code: 'KeyX', shiftKey: true })).toBe('x')
  })
})

describe('isPracticeCharacterCorrect', () => {
  it('is false for an undefined target (input past the end)', () => {
    expect(isPracticeCharacterCorrect('a', undefined, false)).toBe(false)
    expect(isPracticeCharacterCorrect('a', undefined, true)).toBe(false)
  })

  it('honors case sensitivity', () => {
    expect(isPracticeCharacterCorrect('A', 'a', false)).toBe(false)
    expect(isPracticeCharacterCorrect('A', 'a', true)).toBe(true)
    expect(isPracticeCharacterCorrect('a', 'a', false)).toBe(true)
  })

  it('still distinguishes accents in ignore-case mode', () => {
    expect(isPracticeCharacterCorrect('é', 'e', true)).toBe(false)
    expect(isPracticeCharacterCorrect('b', 'a', true)).toBe(false)
  })
})

describe('per-character input states', () => {
  it('marks each typed character against the target', () => {
    expect(getPracticeInputCharacterStates('xbc', 'abc', false)).toEqual([
      { character: 'x', isCorrect: false },
      { character: 'b', isCorrect: true },
      { character: 'c', isCorrect: true },
    ])
  })

  it('marks characters typed past the end as wrong', () => {
    const states = getPracticeInputCharacterStates('abcd', 'abc', false)
    expect(states).toHaveLength(4)
    expect(states[3]).toEqual({ character: 'd', isCorrect: false })
  })

  it('finds the first wrong position', () => {
    expect(getFirstWrongCharacterIndex('abc', 'abc', false)).toBe(-1)
    expect(getFirstWrongCharacterIndex('abd', 'abc', false)).toBe(2)
    expect(getFirstWrongCharacterIndex('xbc', 'abc', false)).toBe(0)
    expect(getFirstWrongCharacterIndex('', 'abc', false)).toBe(-1)
    expect(getFirstWrongCharacterIndex('abcd', 'abc', false)).toBe(3)
  })
})

describe('whole-input helpers', () => {
  it('treats complete as equal length only', () => {
    expect(isWholePracticeInputComplete('abc', 'abc')).toBe(true)
    expect(isWholePracticeInputComplete('ab', 'abc')).toBe(false)
    expect(isWholePracticeInputComplete('abcd', 'abc')).toBe(false)
  })

  it('treats correct as complete and no wrong character', () => {
    expect(isWholePracticeInputCorrect('abc', 'abc', false)).toBe(true)
    expect(isWholePracticeInputCorrect('ab', 'abc', false)).toBe(false)
    expect(isWholePracticeInputCorrect('abx', 'abc', false)).toBe(false)
    expect(isWholePracticeInputCorrect('ABC', 'abc', true)).toBe(true)
    expect(isWholePracticeInputCorrect('ABC', 'abc', false)).toBe(false)
  })

  it('rewinds the input to the last correct prefix on wrong backspace', () => {
    expect(getWholeInputAfterWrongBackspace('abx', 'abc', false)).toBe('ab')
    expect(getWholeInputAfterWrongBackspace('axc', 'abc', false)).toBe('a')
    expect(getWholeInputAfterWrongBackspace('abc', 'abc', false)).toBe('ab')
    expect(getWholeInputAfterWrongBackspace('', 'abc', false)).toBe('')
  })
})
