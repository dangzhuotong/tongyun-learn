import { describe, expect, it } from 'vitest'
import {
  buildMeaningChoices,
  buildSession,
  buildWordChoices,
  pickNewWords,
  resolveSpell,
} from './study'
import { DAY, dailyNewBudget, orderedLevels, remainingNewBudget, type WordEntry, type WordStat } from './wordlist'

const mk = (word: string, level: number, extra: Partial<WordEntry> = {}): WordEntry => ({
  word,
  level,
  phonetic: '/x/',
  meaning: `${word} 的意思`,
  example: `Use ${word} here.`,
  example_zh: '例句',
  tag: 'ai',
  source: '自编',
  ...extra,
})

const stat = (over: Partial<WordStat> = {}): WordStat => ({
  right: 0,
  wrong: 0,
  last: 0,
  box: 0,
  due: 0,
  first: 0,
  taught: true,
  ...over,
})

const NOW = 1_800_000_000_000

describe('level order and daily new-word budget', () => {
  it('introduces levels L1→L2→L3→L5→L4, L6 only when opted in', () => {
    expect(orderedLevels()).toEqual([1, 2, 3, 5, 4])
    expect(orderedLevels([6])).toEqual([1, 2, 3, 5, 4, 6])
  })

  it('drops new words when too many reviews are due', () => {
    expect(dailyNewBudget(0)).toBe(8)
    expect(dailyNewBudget(40)).toBe(8)
    expect(dailyNewBudget(41)).toBe(3)
    expect(dailyNewBudget(80)).toBe(3)
    expect(dailyNewBudget(81)).toBe(0)
    expect(remainingNewBudget(0, 5)).toBe(3)
    expect(remainingNewBudget(81, 0)).toBe(0)
  })

  it('fills new words across levels in order, skipping taught ones', () => {
    const list = [mk('a', 1), mk('b', 1), mk('c', 2), mk('d', 3), mk('e', 5), mk('f', 4)]
    const stats: Record<string, WordStat> = { a: stat({ taught: true }) }
    expect(pickNewWords(list, stats, [], 3).map(w => w.word)).toEqual(['b', 'c', 'd'])
    expect(pickNewWords(list, stats, [], 10).map(w => w.word)).toEqual(['b', 'c', 'd', 'e', 'f'])
  })
})

describe('buildSession', () => {
  const list = [mk('alpha', 1), mk('beta', 2), mk('gamma', 3), mk('delta', 5), mk('eps', 4)]
  const stats: Record<string, WordStat> = {
    alpha: stat({ box: 0, due: NOW - 30 * DAY, first: NOW - 2 * DAY, taught: true }),
    beta: stat({ box: 2, due: NOW - 20 * DAY, first: NOW - 5 * DAY, taught: true }),
    gamma: stat({ box: 0, due: NOW + 10 * DAY, first: NOW - DAY, taught: true }),
    delta: stat({ box: 0, due: NOW - 10 * DAY, first: NOW - 3 * DAY, taught: false }),
  }

  it('puts due reviews first, then new words, with the right modes', () => {
    const plan = buildSession(list, stats, [], NOW, () => 0)
    expect(plan.dueTotal).toBe(2)
    expect(plan.newTotal).toBe(1)
    expect(plan.items.map(i => `${i.mode}:${i.word.word}:${i.reason}`)).toEqual([
      'choice:alpha:review',
      'hint_spell:alpha:review',
      'spell:beta:review',
      'teach:delta:relearn',
      'teach:eps:new',
    ])
    expect(plan.items[0].reviewIndex).toBe(0)
    expect(plan.items[2].reviewIndex).toBe(2)
  })

  it('puts the second review of a box-0 word as hint_spell for the same word', () => {
    const plan = buildSession(list, stats, [], NOW, () => 0)
    expect(plan.items[1].word.word).toBe('alpha')
    expect(plan.items[1].mode).toBe('hint_spell')
  })

  it('counts today-introduced words against the budget and stops new words when swamped', () => {
    const introduced: Record<string, WordStat> = {
      alpha: stat({ box: 0, due: NOW - DAY, first: NOW }),
      beta: stat({ box: 1, due: NOW - DAY, first: NOW }),
      gamma: stat({ box: 1, due: NOW - DAY, first: NOW }),
    }
    const plan = buildSession(list, introduced, [], NOW, () => 0)
    expect(plan.dueTotal).toBe(3)
    expect(plan.newTotal).toBe(2)

    const bigList = [...list, ...Array.from({ length: 81 }, (_, i) => mk(`w${i}`, 1))]
    const heavy: Record<string, WordStat> = {}
    for (let i = 0; i < 81; i += 1) heavy[`w${i}`] = stat({ box: 1, due: NOW - DAY })
    const stopped = buildSession(bigList, heavy, [], NOW, () => 0)
    expect(stopped.dueTotal).toBe(81)
    expect(stopped.newTotal).toBe(0)
  })
})

describe('choice options', () => {
  const pool = [mk('alpha', 1), mk('bravo', 1), mk('charlie', 1), mk('delta', 1), mk('echo', 2)]

  it('offers four unique word options including the answer', () => {
    const options = buildWordChoices(pool[0]!, pool, () => 0.3)
    expect(options).toHaveLength(4)
    expect(new Set(options).size).toBe(4)
    expect(options).toContain('alpha')
  })

  it('offers meaning options for the listen variant', () => {
    const options = buildMeaningChoices(pool[0]!, pool, () => 0.6)
    expect(options).toHaveLength(4)
    expect(options).toContain('alpha 的意思')
  })
})

describe('resolveSpell ladder and re-teach', () => {
  it('advances the 1/3/7/14/30 ladder on correct', () => {
    let s = stat({ last: NOW, box: 0, due: NOW, taught: true })
    s = resolveSpell(s, true, 0, NOW).stat
    expect(s.due - NOW).toBe(3 * DAY)
    s = resolveSpell(s, true, 0, NOW).stat
    expect(s.due - NOW).toBe(7 * DAY)
    s = resolveSpell(s, true, 0, NOW).stat
    expect(s.due - NOW).toBe(14 * DAY)
    s = resolveSpell(s, true, 0, NOW).stat
    expect(s.due - NOW).toBe(30 * DAY)
    s = resolveSpell(s, true, 0, NOW).stat
    expect(s.due - NOW).toBe(30 * DAY)
  })

  it('hints on the first miss and re-teaches on the second', () => {
    const s = stat({ last: NOW - DAY, box: 1, due: NOW - DAY, first: NOW - DAY, taught: true })
    const hinted = resolveSpell(s, false, 0, NOW)
    expect(hinted.action).toBe('hint')
    expect(hinted.stat).toEqual(s)
    const reteach = resolveSpell(s, false, 1, NOW)
    expect(reteach.action).toBe('reteach')
    expect(reteach.stat.taught).toBe(false)
    expect(reteach.stat.box).toBe(0)
    expect(reteach.stat.due).toBe(NOW)
    expect(reteach.stat.first).toBe(s.first)
  })
})
