// tongyun: 课程表排课核心调度器 (Pure scheduler)
import type {
  CurriculumCard,
  SchedulerInput,
  SchedulerResult,
  SubjectConfig,
  SubjectStage,
} from './types'

export const DAY_MS = 24 * 3600 * 1000

export const STAGE_WEIGHTS: Record<SubjectStage, number> = {
  main: 3,
  maintain: 2,
  light: 1,
}

export function isProjectCard(card: CurriculumCard): boolean {
  if (card.isProject) return true
  if (card.type === 'project') return true
  if (Array.isArray(card.tags) && card.tags.includes('project')) return true
  return false
}

/**
 * 各学科每日新卡默认上限：
 * - en: 8
 * - java / ai 在 main 阶段: 6
 * - maintain: 0-2（默认 2）
 * - 其余: 0-3（默认 3）
 */
export function getDefaultNewCardCap(subject: SubjectConfig): number {
  if (subject.dailyNewCap !== undefined) {
    return subject.dailyNewCap
  }
  const sid = (subject.id || '').toLowerCase()
  if (sid === 'en' || sid === 'english') {
    return 8
  }
  if ((sid === 'java' || sid === 'ai') && subject.stage === 'main') {
    return 6
  }
  if (subject.stage === 'maintain') {
    return 2
  }
  return 3
}

/**
 * 规范化 7 天正确率并计算最终可用新卡上限：
 * 7 天正确率 < 70% 时，该学科新卡上限减半（Math.floor(cap / 2)）；70% 边界不减半。
 */
export function calculateSubjectNewCap(subject: SubjectConfig): number {
  const baseCap = getDefaultNewCardCap(subject)
  if (subject.accuracy7d === undefined) {
    return baseCap
  }
  const acc = subject.accuracy7d > 1 ? subject.accuracy7d / 100 : subject.accuracy7d
  if (acc < 0.70) {
    return Math.floor(baseCap / 2)
  }
  return baseCap
}

/**
 * 获取学科弱项系数：
 * 若未显式传入 weakness，则根据 7 天正确率计算（1 - accuracy），默认 1
 */
export function getSubjectWeakness(subject: SubjectConfig): number {
  if (subject.weakness !== undefined) {
    return subject.weakness
  }
  if (subject.accuracy7d !== undefined) {
    const acc = subject.accuracy7d > 1 ? subject.accuracy7d / 100 : subject.accuracy7d
    return Math.max(0, 1 - acc)
  }
  return 1
}

/**
 * 阶段权重 (main 3 / maintain 2 / light 1) × 弱项系数
 */
export function getSubjectScore(subject: SubjectConfig): number {
  const weight = STAGE_WEIGHTS[subject.stage] ?? 1
  const weakness = getSubjectWeakness(subject)
  return weight * weakness
}

/**
 * 格式化结算屏幕文案：今天到期N、已复习M、本周X天, no countdown/streak
 */
export function formatEndScreenSummary(dueTotal: number, reviewedTotal: number, weekDays: number): string {
  return `今天到期${dueTotal}、已复习${reviewedTotal}、本周${weekDays}天`
}

/**
 * Pure scheduler 核心排课算法：
 * 1) 到期复习优先，按逾期天数降序排序，每日复习上限 60；复习卡片不占用新卡学科名额
 * 2) 新卡选择 2-3 个学科：按阶段权重 (main3/maintain2/light1) x 弱项排序选取
 * 3) 各学科每日新卡上限可配置（en 8, java/ai main 6, maintain 0-2, others 0-3）
 *    - 7 天正确率 < 70% -> 该学科新卡减半
 *    - 逾期积压 overdue backlog > 50 -> 今日暂停新卡
 *    - light 学科每周 <= 1-2 次
 *    - project 卡片永不进每日队列
 */
export function scheduleCurriculum(input: SchedulerInput): SchedulerResult {
  const now = input.now ?? Date.now()
  const dailyReviewCap = input.dailyReviewCap ?? 60
  const minNewSubjects = input.minNewSubjects ?? 2
  const maxNewSubjects = input.maxNewSubjects ?? 3

  // 1. 过滤并排序到期复习卡片（项目卡片排除）
  const rawReviews = (input.reviews || []).filter(c => !isProjectCard(c))
  const dueReviews: { card: CurriculumCard; daysOverdue: number }[] = []

  for (const card of rawReviews) {
    const isDue =
      card.daysOverdue !== undefined
        ? card.daysOverdue >= 0
        : card.due !== undefined
          ? card.due <= now
          : true

    if (isDue) {
      const daysOverdue =
        card.daysOverdue !== undefined
          ? card.daysOverdue
          : card.due !== undefined
            ? Math.max(0, (now - card.due) / DAY_MS)
            : 0
      dueReviews.push({ card, daysOverdue })
    }
  }

  // 按逾期天数降序排序（逾期越久越排在最前）
  dueReviews.sort((a, b) => {
    if (b.daysOverdue !== a.daysOverdue) {
      return b.daysOverdue - a.daysOverdue
    }
    return (a.card.due ?? 0) - (b.card.due ?? 0)
  })

  // 逾期积压数：以 input.overdueBacklog 为准，若未传则为到期总数
  const overdueBacklog =
    input.overdueBacklog !== undefined ? input.overdueBacklog : dueReviews.length

  // 每日复习上限 60
  const reviewItems = dueReviews.slice(0, dailyReviewCap).map(d => d.card)
  const dueTotal = dueReviews.length

  // 2. 检查 overdue backlog > 50 熔断规则
  const newCardsBlockedByBacklog = overdueBacklog > 50

  const selectedSubjects: string[] = []
  const newItems: CurriculumCard[] = []
  const subjectAllocations: Record<string, number> = {}

  if (!newCardsBlockedByBacklog) {
    // 3. 筛选可排新卡的候选学科
    const eligibleSubjects = input.subjects.filter(subj => {
      // light 学科每周 <= 1-2 次
      if (subj.stage === 'light') {
        const maxTimes = subj.maxLightTimesPerWeek ?? 2
        const trained = subj.trainedThisWeek ?? 0
        if (trained >= maxTimes) {
          return false
        }
      }
      return true
    })

    // 按 stage weight * weakness 降序排序
    eligibleSubjects.sort((a, b) => getSubjectScore(b) - getSubjectScore(a))

    // 选取 2-3 个学科（若不足 2 个则取全部可用）
    const targetCount = Math.min(
      eligibleSubjects.length,
      Math.max(minNewSubjects, Math.min(maxNewSubjects, eligibleSubjects.length))
    )
    const pickedSubjects = eligibleSubjects.slice(0, targetCount)

    // 标准化 newCards 池
    const newCardsBySubject: Record<string, CurriculumCard[]> = {}
    if (Array.isArray(input.newCards)) {
      for (const card of input.newCards) {
        if (isProjectCard(card)) continue
        const sid = (card.subject || '').toLowerCase()
        if (!newCardsBySubject[sid]) newCardsBySubject[sid] = []
        newCardsBySubject[sid]!.push(card)
      }
    } else if (input.newCards) {
      for (const [sid, cards] of Object.entries(input.newCards)) {
        newCardsBySubject[sid.toLowerCase()] = (cards || []).filter(c => !isProjectCard(c))
      }
    }

    // 为每个选中学科按上限分配新卡
    for (const subj of pickedSubjects) {
      selectedSubjects.push(subj.id)
      const cap = calculateSubjectNewCap(subj)
      subjectAllocations[subj.id] = cap

      const sid = subj.id.toLowerCase()
      const pool = newCardsBySubject[sid] || []
      const allocated = pool.slice(0, cap)
      newItems.push(...allocated)
    }
  }

  const items = [...reviewItems, ...newItems]
  const weekDays = input.trainedDatesThisWeek ?? 1

  return {
    items,
    reviewItems,
    newItems,
    dueTotal,
    reviewedTotal: 0,
    weekDays,
    selectedSubjects,
    overdueBacklog,
    newCardsBlockedByBacklog,
    subjectAllocations,
  }
}
