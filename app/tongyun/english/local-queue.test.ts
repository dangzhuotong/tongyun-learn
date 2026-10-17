import { describe, expect, it } from 'vitest'
import { entryToSteps, roundToQueue, typeableSentence } from './local-queue'
import { splitPhonetics, DAY, nextStat, normalizeStat, pickRound, toneOf, type WordEntry } from './wordlist'

const mk = (word: string, level: number, extra: Partial<WordEntry> = {}): WordEntry => ({
  word, level, phonetic: '/x/', meaning: 'n. 词', example: `Use ${word} here.`, example_zh: '例句', tag: 'ai', source: '自编', ...extra,
})
const list = [...Array.from({ length: 12 }, (_, i) => mk('a' + i, 1)), mk('b0', 2)]
const NOW = 1_800_000_000_000

describe('wordlist v0.2 queue', () => {
  it('builds recall card then sentence card', () => {
    const s = entryToSteps(mk('ensure', 1), 0)
    expect(s.map(x => x.stage)).toEqual(['A', 'B'])
    expect(s[0].recall).toBe(true)
    expect(s[0].tag).toBe('AI')
    expect(s[1].sentence).toBe('Use ensure here.')
  })
  it('makes tweet-style examples typeable', () => {
    expect(typeableSentence('We shipped it today 🚀')).toBe('We shipped it today')
    expect(typeableSentence('> Write tests first.\nThis. 100%.')).toBe('This. 100%.')
    expect(typeableSentence("It's open weights, not open source — no data.")).toBe("It's open weights, not open source - no data.")
  })
  it('labels slang tone', () => {
    expect(toneOf({ meaning: 'adj. 俚 完蛋了', tag: 'community' })).toContain('俚语')
    expect(toneOf({ meaning: 'abbr. 说实话', tag: 'community' })).toContain('缩写')
    expect(toneOf({ meaning: 'n. 并发', tag: 'java' })).toBe('')
    expect(toneOf({ meaning: 'x', tag: 'community', tone: '讽刺' })).toBe('讽刺')
  })
  it('is linear within a level and never jumps level', () => {
    expect(pickRound(list, 1, {}, {}, NOW).map(w => w.word)).toEqual(Array.from({ length: 10 }, (_, i) => 'a' + i))
    const r2 = pickRound(list, 1, {}, { 1: 10 }, NOW)
    expect(r2.map(w => w.word)).toEqual(['a10', 'a11'])
    expect(roundToQueue(r2, 1).items.every(i => i.unitTitle.startsWith('L1'))).toBe(true)
  })
  it('reviews due words first, skips not-yet-due', () => {
    const stats = {
      a3: { right: 1, wrong: 0, last: NOW - 2 * DAY, box: 0, due: NOW - DAY },
      a4: { right: 1, wrong: 0, last: NOW, box: 0, due: NOW + DAY },
    }
    const r = pickRound(list, 1, stats, { 1: 10 }, NOW).map(w => w.word)
    expect(r[0]).toBe('a3')
    expect(r).not.toContain('a4')
  })
})

describe('phonetics', () => {
  it('splits comma readings', () => {
    expect(splitPhonetics('/ɪnˈʃʊə(r)/, /ɪnˈʃɔː(r)/')).toEqual(['/ɪnˈʃʊə(r)/', '/ɪnˈʃɔː(r)/'])
    expect(entryToSteps(mk('default', 3, { phonetic_note: '名词' }), 0)[0].phoneticNote).toBe('名词')
  })
})

describe('spaced repetition 1/3/7/14/30', () => {
  it('walks the ladder and resets on a miss', () => {
    let s = nextStat(undefined, true, NOW)
    expect(s.due - NOW).toBe(1 * DAY)
    const gaps = [3, 7, 14, 30, 30]
    for (const g of gaps) {
      s = nextStat(s, true, NOW)
      expect(s.due - NOW).toBe(g * DAY)
    }
    s = nextStat(s, false, NOW)
    expect(s.box).toBe(0)
    expect(s.due - NOW).toBe(1 * DAY)
  })
  it('migrates old stability data and junk without throwing', () => {
    const old = normalizeStat({ right: 2, wrong: 1, last: NOW, stability: 3 })
    expect(old.box).toBe(2)
    expect(old.due).toBe(NOW + 7 * DAY)
    expect(normalizeStat(null)).toEqual({ right: 0, wrong: 0, last: 0, box: 0, due: 0 })
    expect(normalizeStat({ stability: 'x', last: 'y' }).box).toBe(0)
  })
})

describe('level persistence', () => {
  it('reads a numeric level back', async () => {
    const store = new Map<string, string>()
    ;(globalThis as any).localStorage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k) }
    const { setLevel, getLevel, getStats } = await import('./wordlist')
    setLevel(2)
    expect(getLevel()).toBe(2)
    store.set('tongyun-en-stats-v1', '[1,2]')
    expect(getStats()).toEqual({})
    delete (globalThis as any).localStorage
  })
})
