// tongyun: 学科敲字练习排课队列：优先到期复习，后补新题
import type { Card, QuestionBank, SubjectItemStat, SubjectSessionPlan } from './types'

export function buildSubjectSession(
  bank: QuestionBank,
  stats: Record<string, SubjectItemStat> = {},
  now = Date.now(),
  maxNew = 10
): SubjectSessionPlan {
  const items = bank.items || []

  const dueItems: { item: Card; stat: SubjectItemStat }[] = []
  const newItems: Card[] = []

  for (const it of items) {
    if (it.retired) continue
    const s = stats[it.id]
    if (s && s.last > 0) {
      if (s.due <= now) {
        dueItems.push({ item: it, stat: s })
      }
    } else {
      newItems.push(it)
    }
  }

  dueItems.sort((a, b) => a.stat.due - b.stat.due)

  const pickedNew = maxNew > 0 ? newItems.slice(0, maxNew) : newItems
  const sessionItems: Card[] = [...dueItems.map(d => d.item), ...pickedNew]

  return {
    items: sessionItems,
    dueTotal: dueItems.length,
    newTotal: pickedNew.length,
  }
}

export function getKnowledgePoint(bank: QuestionBank, pointId: string) {
  return bank.points.find(p => p.id === pointId)
}
