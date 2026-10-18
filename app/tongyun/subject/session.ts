// tongyun: 学科敲字练习排课队列：优先到期复习，后补新题
import type { QuestionBank, QuestionItem, SubjectItemStat, SubjectSessionPlan } from './types'

export function buildSubjectSession(
  bank: QuestionBank,
  stats: Record<string, SubjectItemStat> = {},
  now = Date.now(),
  maxNew = 10
): SubjectSessionPlan {
  const items = bank.items || []

  // 到期复习题目（已学过，且 due <= now），到期越早排越前
  const dueItems: { item: QuestionItem; stat: SubjectItemStat }[] = []
  const newItems: QuestionItem[] = []

  for (const it of items) {
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
  const sessionItems: QuestionItem[] = [
    ...dueItems.map(d => d.item),
    ...pickedNew,
  ]

  return {
    items: sessionItems,
    dueTotal: dueItems.length,
    newTotal: pickedNew.length,
  }
}
