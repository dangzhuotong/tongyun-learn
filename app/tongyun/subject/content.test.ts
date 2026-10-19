import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { BANK_IDS, loadBank } from './bank'
import { activeCards, isSelfType, validateBank } from './parse'
import { SUBJECTS, SUBJECT_IDS } from './registry'
import { attachedPoints, isAttachedPoint, mapProgress, pendingPoints } from './map'
import { buildDaySchedule, type NewCard, type ScheduleSubject } from './schedule'
import type { QuestionBank } from './types'

const NEW_SUBJECTS: Record<string, { cards: number; points: number }> = {
  fde: { cards: 30, points: 4 },
  web: { cards: 33, points: 5 },
  writing: { cards: 30, points: 4 },
  ip: { cards: 30, points: 4 },
  tools: { cards: 31, points: 4 },
}

// 「待挂」点：map_point 缺省 / null，排课照常但不计地图进度。
const PENDING_POINTS: Record<string, string[]> = {
  ip: ['ip.github-profile'],
  tools: ['tools.git.basics', 'tools.shell', 'tools.ai-coding'],
  writing: ['write.structure', 'write.clarity', 'write.publish'],
}

const loadAll: Array<[string, () => Promise<QuestionBank>]> = Object.keys(NEW_SUBJECTS).map(id => [
  id,
  () => loadBank(id),
])

describe('导入五科：不修改 id，按 java 兼容结构加载', () => {
  it('六科都注册且都有加载器', () => {
    expect(SUBJECT_IDS).toEqual(['java', 'ai', 'fde', 'web', 'writing', 'ip', 'tools'])
    expect(BANK_IDS).toEqual(SUBJECT_IDS)
  })

  it.each(loadAll)('%s 的卡数与点数固定，subject 一致', async (id, load) => {
    const bank = await load()
    expect(bank.subject).toBe(id)
    expect(bank.items).toHaveLength(NEW_SUBJECTS[id]!.cards)
    expect(bank.points).toHaveLength(NEW_SUBJECTS[id]!.points)
  })

  it('五科合计 154 张卡，id 保持文件原值', async () => {
    let total = 0
    for (const [id, load] of loadAll) {
      const bank = await load()
      total += bank.items.length
      for (const card of bank.items) {
        expect(card.id.startsWith(id === 'writing' ? 'wrt' : id === 'tools' ? 'tool' : id)).toBe(true)
      }
    }
    expect(total).toBe(154)
  })

  it('每个学科都能通过注册表 load 出来', async () => {
    for (const s of SUBJECTS) {
      const bank = await s.load()
      expect(bank.subject).toBe(s.id)
    }
  })
})

describe('字段校验：choice 带 options、oral/project 带 rubric、无结构问题', () => {
  it.each(loadAll)('%s 通过 validateBank', async (id, load) => {
    const bank = await load()
    expect(validateBank(bank)).toEqual([])
  })

  it.each(loadAll)('%s 的 choice 选项 >=3 且 answer 在其中', async (_id, load) => {
    const bank = await load()
    const choices = bank.items.filter(c => c.type === 'choice')
    expect(choices.length).toBeGreaterThan(0)
    for (const c of choices) {
      expect(c.options!.length).toBeGreaterThanOrEqual(3)
      expect(new Set(c.options).size).toBe(c.options!.length)
      expect(c.options).toContain(c.answer)
      expect(c.grading).toBe('auto')
    }
  })

  it.each(loadAll)('%s 的 oral/project rubric 为 3–5 条并走自评', async (_id, load) => {
    const bank = await load()
    const selfCards = bank.items.filter(c => isSelfType(c.type))
    expect(selfCards.length).toBeGreaterThan(0)
    for (const c of selfCards) {
      expect(c.rubric!.length).toBeGreaterThanOrEqual(3)
      expect(c.rubric!.length).toBeLessThanOrEqual(5)
      expect(c.grading).toBe('self')
    }
  })
})

describe('「待挂」：可排课但不计知识地图进度', () => {
  it.each(Object.entries(PENDING_POINTS))('%s 的待挂点识别正确', async (id, ids) => {
    const bank = await loadBank(id)
    expect(pendingPoints(bank).map(p => p.id).sort()).toEqual([...ids].sort())
    for (const p of pendingPoints(bank)) expect(isAttachedPoint(p)).toBe(false)
  })

  it.each(loadAll)('%s 地图进度只数已挂点', async (id, load) => {
    const bank = await load()
    const progress = mapProgress(bank)
    expect(progress.attached).toBe(attachedPoints(bank).length)
    expect(progress.attached + progress.pending).toBe(progress.total)
    expect(progress.total).toBe(bank.points.length)
    const expectedPending = PENDING_POINTS[id]?.length ?? 0
    expect(progress.pending).toBe(expectedPending)
    expect(progress.attached).toBe(bank.points.length - expectedPending)
  })

  it('待挂点的新卡照常被「开始学」排进队列', async () => {
    const bank = await loadBank('tools')
    const pendingIds = new Set(pendingPoints(bank).map(p => p.id))
    const newCards: NewCard[] = activeCards(bank)
      .filter(c => c.type !== 'project')
      .map(c => ({ id: c.id, subject: 'tools', type: c.type }))
    const subject: ScheduleSubject = { id: 'tools', stage: 'main' }
    const plan = buildDaySchedule({
      now: new Date(2026, 9, 19, 12, 0, 0).getTime(),
      subjects: [subject],
      dueCards: [],
      newCards,
      config: { newLimits: { tools: 1000 } },
    })
    const scheduledIds = plan.newCards.map(n => n.card.id)
    expect(scheduledIds.length).toBeGreaterThan(0)
    const scheduledPending = scheduledIds.filter(id => pendingIds.has(pointOf(bank, id)))
    expect(scheduledPending.length).toBeGreaterThan(0)
    // project 不进每日队列
    expect(plan.newCards.every(n => n.card.type !== 'project')).toBe(true)
  })

  it('待挂点的到期卡照常进入复习', async () => {
    const now = new Date(2026, 9, 19, 12, 0, 0).getTime()
    const bank = await loadBank('writing')
    const pendingCard = activeCards(bank).find(c => {
      const point = bank.points.find(p => p.id === c.point_id)
      return point && !isAttachedPoint(point)
    })!
    expect(pendingCard).toBeTruthy()
    const plan = buildDaySchedule({
      now,
      subjects: [{ id: 'writing', stage: 'light' }],
      dueCards: [{ id: pendingCard.id, subject: 'writing', due: now - 1000, type: pendingCard.type }],
      newCards: [],
    })
    expect(plan.reviews.map(r => r.card.id)).toContain(pendingCard.id)
  })
})

function pointOf(bank: QuestionBank, cardId: string): string {
  return bank.items.find(c => c.id === cardId)?.point_id ?? ''
}

describe('无盒上路径：内容目录只放 JSON，代码不引用绝对路径', () => {
  it('bank / registry / map / subjects.json 不含 /workspace 或 seed 路径', () => {
    const dir = resolve(process.cwd(), 'app/tongyun/subject')
    const files = readdirSync(dir).filter(f => !f.endsWith('.test.ts') && f.endsWith('.ts'))
    files.push('subjects.json')
    for (const f of files) {
      const src = readFileSync(resolve(dir, f), 'utf8')
      expect(src).not.toContain('/workspace')
      expect(src).not.toContain('seed/')
      expect(src).not.toContain('docs/tasks')
    }
  })
})
