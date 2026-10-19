import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import {
  DEFAULT_SCHEDULE_CONFIG,
  DAY,
  activeDayCount,
  buildDaySchedule,
  formatDaySummary,
  halveLimit,
  newLimitFor,
  resolveConfig,
  startOfWeek,
  STAGE_WEIGHT,
  type CardType,
  type DueCard,
  type NewCard,
  type ScheduleInput,
  type ScheduleSubject,
} from './schedule'

// 2026-10-19 是周一，用本地时间构造，日/周边界和实现一致。
const NOW = new Date(2026, 9, 19, 12, 0, 0).getTime()

const mkDue = (id: string, subject: string, overdueDays: number, type?: CardType): DueCard => ({
  id,
  subject,
  due: NOW - overdueDays * DAY,
  type,
})

const mkNew = (id: string, subject: string, type?: CardType): NewCard => ({ id, subject, type })

const sub = (id: string, stage: ScheduleSubject['stage'], weakness?: number): ScheduleSubject => ({
  id,
  stage,
  weakness,
})

const base = (over: Partial<ScheduleInput> = {}): ScheduleInput => ({
  now: NOW,
  subjects: [sub('java', 'main')],
  dueCards: [],
  newCards: [],
  ...over,
})

describe('到期复习：按逾期天数排序 + 日复习上限 60', () => {
  it('most overdue first, capped at 60, dueTotal is uncapped', () => {
    const dueCards = Array.from({ length: 65 }, (_, i) => mkDue(`c${i}`, 'java', i + 1))
    const plan = buildDaySchedule(base({ dueCards }))
    expect(plan.dueTotal).toBe(65)
    expect(plan.backlog).toBe(65)
    expect(plan.reviewLimitHit).toBe(true)
    expect(plan.reviews).toHaveLength(60)
    expect(plan.reviews.map(r => r.overdueDays)).toEqual(
      Array.from({ length: 60 }, (_, i) => 65 - i)
    )
    expect(plan.reviews[0]!.card.id).toBe('c64')
  })

  it('exactly 60 is not truncated; 61 is', () => {
    const sixty = Array.from({ length: 60 }, (_, i) => mkDue(`c${i}`, 'java', i + 1))
    expect(buildDaySchedule(base({ dueCards: sixty })).reviewLimitHit).toBe(false)
    expect(buildDaySchedule(base({ dueCards: sixty })).reviews).toHaveLength(60)

    const sixtyOne = Array.from({ length: 61 }, (_, i) => mkDue(`c${i}`, 'java', i + 1))
    const plan = buildDaySchedule(base({ dueCards: sixtyOne }))
    expect(plan.reviewLimitHit).toBe(true)
    expect(plan.reviews).toHaveLength(60)
  })

  it('today-due cards report 0 overdue days', () => {
    const plan = buildDaySchedule(base({ dueCards: [mkDue('today', 'java', 0)] }))
    expect(plan.reviews[0]!.overdueDays).toBe(0)
  })

  it('ignores not-yet-due cards', () => {
    const future = { id: 'f', subject: 'java', due: NOW + DAY }
    const plan = buildDaySchedule(base({ dueCards: [future] }))
    expect(plan.dueTotal).toBe(0)
    expect(plan.reviews).toHaveLength(0)
  })
})

describe('挑 2–3 科：阶段权重 × 弱项系数，复习不占名额', () => {
  const subjects = [
    sub('java', 'main'), // 3
    sub('web', 'maintain'), // 2
    sub('tools', 'light'), // 1
    sub('writing', 'light', 3), // 1 × 3 = 3
  ]
  const newCards = ['java', 'web', 'tools', 'writing'].flatMap(s =>
    [0, 1].map(i => mkNew(`${s}-${i}`, s))
  )

  it('caps at 3 new-card subjects, ordered by score with id tie-break', () => {
    const plan = buildDaySchedule(base({ subjects, newCards }))
    // java 3 与 writing 3 同分，按 id 升序：java < writing < web(2)
    expect(plan.subjects).toEqual(['java', 'writing', 'web'])
    expect(plan.subjects).toHaveLength(3)
  })

  it('reviews from unselected subjects still make the queue', () => {
    const plan = buildDaySchedule(
      base({
        subjects,
        newCards,
        dueCards: subjects.map((s, i) => mkDue(`due-${s.id}`, s.id, i + 1)),
      })
    )
    expect(plan.subjects).not.toContain('tools')
    expect(plan.reviews.map(r => r.card.subject).sort()).toEqual(
      ['java', 'tools', 'web', 'writing'].sort()
    )
  })

  it('picks whatever is eligible when fewer than 2 subjects exist', () => {
    const plan = buildDaySchedule(
      base({ subjects: [sub('only', 'light')], newCards: [mkNew('n', 'only')] })
    )
    expect(plan.subjects).toEqual(['only'])
  })

  it('exposes 3/2/1 stage weights', () => {
    expect(STAGE_WEIGHT.main).toBe(3)
    expect(STAGE_WEIGHT.maintain).toBe(2)
    expect(STAGE_WEIGHT.light).toBe(1)
  })
})

describe('每科新卡上限按表，可配置', () => {
  it('english 8, java 6, ai 6 from the default table', () => {
    const subjects = [sub('english', 'main'), sub('java', 'main'), sub('ai', 'main')]
    const newCards = subjects.flatMap(s =>
      Array.from({ length: 10 }, (_, i) => mkNew(`${s.id}-${i}`, s.id))
    )
    const plan = buildDaySchedule(base({ subjects, newCards }))
    const counts = Object.fromEntries(
      ['english', 'java', 'ai'].map(id => [id, plan.newCards.filter(n => n.subject === id).length])
    )
    expect(counts).toEqual({ english: 8, java: 6, ai: 6 })
  })

  it('unknown subject falls back to defaultNewLimit', () => {
    const plan = buildDaySchedule(
      base({
        subjects: [sub('fde', 'main')],
        newCards: Array.from({ length: 10 }, (_, i) => mkNew(`f${i}`, 'fde')),
      })
    )
    expect(plan.newCards).toHaveLength(DEFAULT_SCHEDULE_CONFIG.defaultNewLimit)
  })

  it('config overrides the per-subject table', () => {
    const config = resolveConfig({ newLimits: { english: 2 } })
    expect(newLimitFor('english', config)).toBe(2)
    expect(newLimitFor('java', config)).toBe(6)
    const plan = buildDaySchedule(
      base({
        subjects: [sub('english', 'main')],
        newCards: Array.from({ length: 10 }, (_, i) => mkNew(`e${i}`, 'english')),
        config,
      })
    )
    expect(plan.newCards).toHaveLength(2)
  })
})

describe('近 7 天正确率 <70% 新卡减半（边界 70%）', () => {
  const cards = Array.from({ length: 10 }, (_, i) => mkNew(`e${i}`, 'english'))

  it('exactly 70% is not halved', () => {
    const plan = buildDaySchedule(
      base({
        subjects: [sub('english', 'main')],
        newCards: cards,
        accuracy: [{ subject: 'english', attempts: 10, correct: 7 }],
      })
    )
    expect(plan.newCards).toHaveLength(8)
    expect(plan.newCards.every(n => n.halved === false)).toBe(true)
  })

  it('69% is halved to half of the limit', () => {
    const plan = buildDaySchedule(
      base({
        subjects: [sub('english', 'main')],
        newCards: cards,
        accuracy: [{ subject: 'english', attempts: 100, correct: 69 }],
      })
    )
    expect(plan.newCards).toHaveLength(4)
    expect(plan.newCards.every(n => n.halved === true)).toBe(true)
    expect(plan.newCards[0]!.limit).toBe(4)
  })

  it('a weak subject is still halved even when weakness boosted its selection score', () => {
    const plan = buildDaySchedule(
      base({
        subjects: [sub('java', 'main'), sub('english', 'main')],
        newCards: [
          ...Array.from({ length: 10 }, (_, i) => mkNew(`j${i}`, 'java')),
          ...Array.from({ length: 10 }, (_, i) => mkNew(`e${i}`, 'english')),
        ],
        accuracy: [{ subject: 'java', attempts: 10, correct: 5 }],
      })
    )
    expect(plan.newCards.filter(n => n.subject === 'java')).toHaveLength(3)
    expect(plan.newCards.filter(n => n.subject === 'english')).toHaveLength(8)
  })

  it('halveLimit helper handles odd and zero limits', () => {
    expect(halveLimit(8)).toBe(4)
    expect(halveLimit(6)).toBe(3)
    expect(halveLimit(7)).toBe(4)
    expect(halveLimit(0)).toBe(0)
  })
})

describe('到期积压 >50 当天不出新卡（边界 50）', () => {
  const newCards = [mkNew('n1', 'java')]
  const dueN = (n: number) => Array.from({ length: n }, (_, i) => mkDue(`c${i}`, 'java', i + 1))

  it('exactly 50 due still allows new cards', () => {
    const plan = buildDaySchedule(base({ dueCards: dueN(50), newCards }))
    expect(plan.stoppedNewCards).toBe(false)
    expect(plan.newCards).toHaveLength(1)
  })

  it('51 due stops new cards for the day', () => {
    const plan = buildDaySchedule(base({ dueCards: dueN(51), newCards }))
    expect(plan.stoppedNewCards).toBe(true)
    expect(plan.newCards).toEqual([])
    expect(plan.subjects).toEqual([])
  })

  it('project due cards do not count toward the backlog threshold', () => {
    const dueCards = Array.from({ length: 60 }, (_, i) => mkDue(`p${i}`, 'java', i + 1, 'project'))
    const plan = buildDaySchedule(base({ dueCards, newCards }))
    expect(plan.dueTotal).toBe(0)
    expect(plan.stoppedNewCards).toBe(false)
    expect(plan.newCards).toHaveLength(1)
  })
})

describe('light 科每周 ≤1–2 次', () => {
  const subjects = [sub('tools', 'light')]
  const newCards = [mkNew('t1', 'tools')]

  it('used once is still eligible (default limit 2)', () => {
    const plan = buildDaySchedule(base({ subjects, newCards, lightUsedThisWeek: { tools: 1 } }))
    expect(plan.subjects).toEqual(['tools'])
  })

  it('used twice is excluded', () => {
    const plan = buildDaySchedule(base({ subjects, newCards, lightUsedThisWeek: { tools: 2 } }))
    expect(plan.subjects).toEqual([])
    expect(plan.newCards).toEqual([])
  })

  it('respects a custom weekly limit', () => {
    const plan = buildDaySchedule(
      base({
        subjects,
        newCards,
        lightUsedThisWeek: { tools: 1 },
        config: { lightWeeklyLimit: 1 },
      })
    )
    expect(plan.subjects).toEqual([])
  })
})

describe('project 不进每日队列', () => {
  it('project-stage subjects never get new cards', () => {
    const plan = buildDaySchedule(
      base({ subjects: [sub('proj', 'project')], newCards: [mkNew('p1', 'proj')] })
    )
    expect(plan.subjects).toEqual([])
    expect(plan.newCards).toEqual([])
  })

  it('project-typed new cards are filtered out', () => {
    const plan = buildDaySchedule(
      base({
        subjects: [sub('java', 'main')],
        newCards: [mkNew('n1', 'java'), mkNew('p1', 'java', 'project')],
      })
    )
    expect(plan.newCards.map(n => n.card.id)).toEqual(['n1'])
  })

  it('project-typed due cards are filtered out of reviews', () => {
    const plan = buildDaySchedule(
      base({ dueCards: [mkDue('r1', 'java', 1), mkDue('p1', 'java', 1, 'project')] })
    )
    expect(plan.reviews.map(r => r.card.id)).toEqual(['r1'])
    expect(plan.dueTotal).toBe(1)
  })
})

describe('完成显示：今天到期 / 已复习 / 本周天数，无倒计时或连续天数', () => {
  it('summary carries dueToday, reviewed and weekDays', () => {
    const plan = buildDaySchedule(
      base({ dueCards: [mkDue('a', 'java', 1), mkDue('b', 'java', 2)], reviewedToday: 12, weekDays: 3 })
    )
    expect(plan.summary).toEqual({ dueToday: 2, reviewed: 12, weekDays: 3 })
  })

  it('formats exactly 今天到期N、已复习M、本周X天', () => {
    const text = formatDaySummary({ dueToday: 2, reviewed: 12, weekDays: 3 })
    expect(text).toBe('今天到期2、已复习12、本周3天')
    expect(text).not.toMatch(/倒计时|连续|连击|streak|countdown/i)
  })

  it('activeDayCount counts distinct days in the current week only', () => {
    const mon = new Date(2026, 9, 19, 9, 0, 0).getTime()
    const tue = new Date(2026, 9, 20, 9, 0, 0).getTime()
    const lastWeek = new Date(2026, 9, 12, 9, 0, 0).getTime()
    const fri = new Date(2026, 9, 23, 12, 0, 0).getTime()
    expect(startOfWeek(NOW)).toBe(new Date(2026, 9, 19, 0, 0, 0).getTime())
    expect(startOfWeek(fri)).toBe(new Date(2026, 9, 19, 0, 0, 0).getTime())
    expect(activeDayCount([mon, mon, tue, lastWeek], fri)).toBe(2)
  })
})

describe('纯函数：同样输入同样输出', () => {
  it('is deterministic and does not mutate the input', () => {
    const input = base({
      subjects: [sub('java', 'main'), sub('web', 'maintain')],
      dueCards: [mkDue('a', 'java', 2), mkDue('b', 'web', 5)],
      newCards: [mkNew('n', 'java')],
      reviewedToday: 1,
      weekDays: 2,
    })
    const snapshot = JSON.parse(JSON.stringify(input))
    const first = buildDaySchedule(input)
    const second = buildDaySchedule(input)
    expect(second).toEqual(first)
    expect(JSON.parse(JSON.stringify(input))).toEqual(snapshot)
  })
})

describe('首页仍只有一个「开始学」按钮', () => {
  it('index.vue contains exactly one start-learn button', () => {
    const source = readFileSync(new URL('../../pages/index.vue', import.meta.url), 'utf8')
    expect(source.match(/data-testid="start-learn"/g) ?? []).toHaveLength(1)
    expect(source.match(/<button/g) ?? []).toHaveLength(1)
  })
})
