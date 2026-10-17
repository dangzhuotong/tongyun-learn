import { describe, expect, it } from 'vitest'
import { entryToSteps, roundToQueue } from './local-queue'
import { pickRound, type WordEntry } from './wordlist'

const mk = (word: string, level: number): WordEntry => ({
  word, level, phonetic: '/x/', meaning: 'n. 词', example: `Use ${word} here.`, example_zh: '例句', tag: 'general', source: '自编',
})
const list = [...Array.from({ length: 12 }, (_, i) => mk('a' + i, 1)), mk('b0', 2)]

describe('wordlist queue', () => {
  it('builds word then sentence steps', () => {
    const s = entryToSteps(mk('ensure', 1), 0)
    expect(s.map(x => x.stage)).toEqual(['A', 'B'])
    expect(s[1].sentence).toBe('Use ensure here.')
    expect(s[0].cardId).toBeNull()
  })
  it('is linear within a level and never jumps level', () => {
    const r1 = pickRound(list, 1, {}, {})
    expect(r1.map(w => w.word)).toEqual(Array.from({ length: 10 }, (_, i) => 'a' + i))
    const r2 = pickRound(list, 1, {}, { 1: 10 })
    expect(r2.map(w => w.word)).toEqual(['a10', 'a11'])
    expect(roundToQueue(r2, 1).items.every(i => i.unitTitle.startsWith('L1'))).toBe(true)
  })
  it('puts unstable learned words first', () => {
    const r = pickRound(list, 1, { a3: { right: 0, wrong: 2, last: 1, stability: 0 } }, { 1: 10 })
    expect(r[0].word).toBe('a3')
  })
})
