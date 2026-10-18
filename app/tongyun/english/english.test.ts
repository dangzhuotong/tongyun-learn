import { afterEach, describe, expect, it } from 'vitest'
import { freshAttempt, isResolved, submitAttempt } from './attempt'
import { adaptCoach, adaptToday } from './adapt'
import { buildTypeEvent, fetchToday, postTypeEvent } from './client'
import { gradeTyped, markLetters } from './grade'

const loose = { strictCase: false, loosePunctuation: true }
const strict = { strictCase: true, loosePunctuation: false }

describe('adaptToday', () => {
  it('maps the documented today payload and keeps A then B', () => {
    const queue = adaptToday({
      unit: { title: '开发英语 · 单元3', progress: 0.25 },
      suggestion: '先把 oppose 敲稳。',
      items: [
        {
          id: '1',
          stage: 'A',
          word_id: 'oppose',
          word: 'oppose',
          phonetic: '/əˈpoʊz/',
          cn: '反对；抵制',
          examples: [{ en: 'We oppose the new policy.', zh: '我们反对这项新政策。' }],
        },
        {
          id: '2',
          stage: 'sentence',
          word_id: 'oppose',
          sentence_id: 's1',
          word: 'oppose',
          sentence_zh: '我将反对改变这个法规',
          sentence: 'I would oppose changing the law.',
        },
      ],
    })

    expect(queue.unitTitle).toBe('开发英语 · 单元3')
    expect(queue.unitProgress).toBe(0.25)
    expect(queue.suggestion).toBe('先把 oppose 敲稳。')
    expect(queue.items.map(item => item.stage)).toEqual(['A', 'B'])
    expect(queue.items[0].examples).toEqual([{ en: 'We oppose the new policy.', zh: '我们反对这项新政策。' }])
    expect(queue.items[0].meaning).toBe('反对；抵制')
    expect(queue.items[1].sentence).toBe('I would oppose changing the law.')
    expect(queue.items[1].promptZh).toBe('我将反对改变这个法规')
    expect(queue.items[1].sentenceId).toBe('s1')
  })

  it('does not invent a sentence step from examples', () => {
    const queue = adaptToday({
      items: [
        {
          stage: 'word',
          word: 'latency',
          examples: [{ en: 'Latency hides in the queue.', zh: '延迟藏在队列里。' }],
        },
      ],
    })
    expect(queue.items).toHaveLength(1)
    expect(queue.items[0].stage).toBe('A')
    expect(queue.items[0].examples[0].en).toContain('Latency')
  })

  it('keeps server order when a sentence comes before the next word', () => {
    const queue = adaptToday({
      queue: [
        { stage: 'B', word: 'oppose', sentence: 'I oppose it.', sentence_zh: '我反对。' },
        { stage: 'A', word: 'latency', cn: '延迟' },
      ],
    })
    expect(queue.items.map(item => `${item.stage}:${item.word}`)).toEqual(['B:oppose', 'A:latency'])
  })

  it('accepts aliased fields and expands an explicit sentence flag in place', () => {
    const queue = adaptToday({
      data: {
        current_unit: { name: '单元3', ratio: 80, track: '开发英语' },
        advice: '加练拼写',
        queue: [
          { stage: 'A', word: 'read', cn: '阅读' },
          {
            phase: 'word',
            card_id: 9,
            spelling: 'latency',
            ipa: '/ˈleɪtənsi/',
            trans: [{ cn: '延迟' }],
            include_sentence: true,
            sentences: [{ text: 'Latency hides in the queue.', translation: '延迟藏在队列里。', id: 'ls1' }],
          },
        ],
      },
    })
    expect(queue.unitTitle).toBe('开发英语 · 单元3')
    expect(queue.unitProgress).toBe(0.8)
    expect(queue.suggestion).toBe('加练拼写')
    expect(queue.items.map(item => item.stage)).toEqual(['A', 'A', 'B'])
    expect(queue.items[1].cardId).toBe(9)
    expect(queue.items[2].cardId).toBe(9)
    expect(queue.items[1].wordId).toBe('')
    expect(queue.items[1].meaning).toBe('延迟')
    expect(queue.items[1].phonetic).toBe('/ˈleɪtənsi/')
    expect(queue.items[2].sentence).toBe('Latency hides in the queue.')
    expect(queue.items[2].promptZh).toBe('延迟藏在队列里。')
    expect(queue.items[2].sentenceId).toBe('ls1')
  })

  it('uses payload.sentences as examples unless the item asks to type them', () => {
    const shown = adaptToday({
      items: [{ word: 'token', meaning: '词元', payload: { sentences: [{ en: 'Count the tokens.', zh: '数一下词元。' }] } }],
    })
    expect(shown.items).toHaveLength(1)
    expect(shown.items[0].examples[0].en).toBe('Count the tokens.')

    const typed = adaptToday({
      items: [
        {
          word: 'token',
          stages: ['A', 'B'],
          payload: { sentences: [{ en: 'Count the tokens.', zh: '数一下词元。' }] },
        },
      ],
    })
    expect(typed.items.map(item => item.stage)).toEqual(['A', 'B'])
  })
})

describe('adaptCoach', () => {
  it('reads summary, weak points, and the week plan under alternate keys', () => {
    const coach = adaptCoach({
      data: {
        one_liner: 'oppose 的拼写还不稳。',
        nails: [{ headword: 'oppose', reason: '拼写', error_text: '少写了一个 p', wrong_count: 3 }],
        week_plan: ['加练 oppose 的例句', { title: '先别开新单元', note: '正确率还没稳住' }],
      },
    })
    expect(coach.summary).toBe('oppose 的拼写还不稳。')
    expect(coach.weak[0]).toEqual({ word: 'oppose', tag: '拼写', detail: '少写了一个 p', count: 3 })
    expect(coach.plan.map(item => item.title)).toEqual(['加练 oppose 的例句', '先别开新单元'])
  })
})

describe('grading and one correction', () => {
  it('matches words without case, and sentences with loose punctuation', () => {
    expect(gradeTyped('Oppose', 'oppose', 'A', loose)).toBe(true)
    expect(gradeTyped('Oppose', 'oppose', 'A', strict)).toBe(false)
    expect(gradeTyped("I would oppose changing the law!", 'I would oppose changing the law.', 'B', loose)).toBe(true)
    expect(gradeTyped('i would oppose changing the law.', 'I would oppose changing the law.', 'B', strict)).toBe(false)
    expect(gradeTyped('I oppose the law.', 'I would oppose changing the law.', 'B', loose)).toBe(false)
  })

  it('marks typed letters against the target word', () => {
    expect(markLetters('oppose', 'op', loose)).toEqual(['ok', 'ok', 'next', 'left', 'left', 'left'])
    expect(markLetters('oppose', 'opx', loose)[2]).toBe('bad')
  })

  it('records a first-try success, a used correction, and a second miss', () => {
    const first = submitAttempt({ ...freshAttempt(), typed: 'oppose' }, 'oppose', 'A', loose)
    expect(first.phase).toBe('done')
    expect(first.correct).toBe(true)
    expect(isResolved(first)).toBe(true)

    const missed = submitAttempt({ ...freshAttempt(), typed: 'opose' }, 'oppose', 'A', loose)
    expect(missed.phase).toBe('editing')
    expect(missed.failures).toBe(1)
    expect(missed.hint).toBe('再改一次')

    const fixed = submitAttempt({ ...missed, typed: 'oppose' }, 'oppose', 'A', loose)
    expect(fixed.phase).toBe('hold')
    expect(fixed.correct).toBe(false)
    expect(fixed.usedCorrection).toBe(true)
    expect(fixed.eventTyped).toBe('opose')

    const again = submitAttempt({ ...missed, typed: 'opose' }, 'oppose', 'A', loose)
    expect(again.phase).toBe('hold')
    expect(again.correct).toBe(false)
    expect(again.hint).toContain('oppose')
  })
})

describe('english learn client', () => {
  const originalFetch = globalThis.fetch

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('does not call the network without a token', async () => {
    globalThis.fetch = (() => {
      throw new Error('should not fetch')
    }) as typeof fetch
    const res = await fetchToday({ url: 'http://127.0.0.1:8031/', token: '' })
    expect(res).toMatchObject({ ok: false, kind: 'no_token', status: 0 })
  })

  it('adapts a today payload from the service', async () => {
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify({
          suggestion: '今天先敲 oppose。',
          items: [{ stage: 'A', word: 'oppose', cn: '反对' }],
        }),
        { status: 200 }
      )) as typeof fetch
    const res = await fetchToday({ url: 'http://127.0.0.1:8031', token: 'web-token' })
    expect(res.ok).toBe(true)
    expect(res.data?.items[0].word).toBe('oppose')
    expect(res.data?.suggestion).toBe('今天先敲 oppose。')
  })

  it('posts a type event with the bearer token', async () => {
    const calls: { url: string; init: RequestInit }[] = []
    globalThis.fetch = (async (url: string, init: RequestInit) => {
      calls.push({ url, init })
      return new Response(JSON.stringify({ ok: true }), { status: 200 })
    }) as typeof fetch

    const step = adaptToday({
      items: [{ id: '1', phase: 'A', card_id: '9', word: 'oppose' }],
    }).items[0]
    expect(step.cardId).toBe(9)
    const missed = submitAttempt({ ...freshAttempt(), typed: 'opose' }, 'oppose', 'A', loose)
    const fixed = submitAttempt({ ...missed, typed: 'oppose' }, 'oppose', 'A', loose)
    const body = buildTypeEvent(step, fixed, 1500.4)
    expect(body).toEqual({ card_id: 9, phase: 'A', typed: 'opose', duration_ms: 1500 })
    const res = await postTypeEvent(body!, { url: 'http://127.0.0.1:8031/', token: 'web-token' })

    expect(res.ok).toBe(true)
    expect(calls[0].url).toBe('http://127.0.0.1:8031/v1/type')
    expect((calls[0].init.headers as Record<string, string>).Authorization).toBe('Bearer web-token')
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      card_id: 9,
      phase: 'A',
      typed: 'opose',
      duration_ms: 1500,
    })
  })

  it('does not invent a type body when the queue item has no card_id', () => {
    const step = adaptToday({ items: [{ stage: 'A', word: 'oppose', word_id: 'oppose' }] }).items[0]
    expect(step.cardId).toBeNull()
    const state = submitAttempt({ ...freshAttempt(), typed: 'oppose' }, 'oppose', 'A', loose)
    expect(buildTypeEvent(step, state, 10)).toBeNull()
  })

  it('classifies a rejected token', async () => {
    globalThis.fetch = (async () =>
      new Response(JSON.stringify({ error: { code: 'unauthorized', message: 'nope' } }), { status: 401 })) as typeof fetch
    const res = await fetchToday({ url: 'http://127.0.0.1:8031/', token: 'nope' })
    expect(res.kind).toBe('bad_token')
  })
})
