// tongyun: 「开始学」按课程表排课（纯函数，不读 localStorage、不发请求）。
// 课程表 4.6：到期复习先行 → 按阶段权重(main3/maintain2/light1)×弱项系数挑 2–3 科
// → 每科新卡上限（英语 8、Java/AI 主线 6 等，可配置）→ 近 7 天正确率 <70% 该科新卡减半
// → 到期积压 >50 当天不出新卡；light 科每周 ≤1–2 次；project 不进每日队列。
// 汇总只显示「今天到期N、已复习M、本周X天」，不做倒计时 / 连续天数。

export const DAY = 24 * 3600 * 1000

export type Stage = 'main' | 'maintain' | 'light' | 'project'
export type CardType = 'code' | 'term' | 'concept' | 'choice' | 'oral' | 'project'

/** 阶段权重：主线 3、维持 2、轻量 1。 */
export const STAGE_WEIGHT: Record<Exclude<Stage, 'project'>, number> = {
  main: 3,
  maintain: 2,
  light: 1,
}

export interface ScheduleSubject {
  id: string
  title?: string
  stage: Stage
  /** 弱项系数；缺省时由近 7 天正确率推导（低于阈值给 1.5，否则 1）。 */
  weakness?: number
}

export interface DueCard {
  id: string
  subject: string
  /** 下次到期时间戳；<= now 表示到期。 */
  due: number
  type?: CardType
}

export interface NewCard {
  id: string
  subject: string
  type?: CardType
}

export interface SubjectAccuracy {
  subject: string
  /** 近 7 天作答数 */
  attempts: number
  /** 近 7 天正确数 */
  correct: number
}

export interface ScheduleConfig {
  /** 日复习上限 */
  dailyReviewLimit: number
  /** 每天最多给几个学科排新卡（2–3 科） */
  maxNewSubjects: number
  /** 到期积压超过这个数当天不出新卡 */
  backlogStop: number
  /** 近 7 天正确率低于该值，新卡减半 */
  lowAccuracy: number
  /** light 科每周最多排几次 */
  lightWeeklyLimit: number
  /** 未在 newLimits 表里的学科默认新卡上限 */
  defaultNewLimit: number
  /** 每科新卡上限表（学科 id → 张数） */
  newLimits: Record<string, number>
}

export const DEFAULT_SCHEDULE_CONFIG: ScheduleConfig = {
  dailyReviewLimit: 60,
  maxNewSubjects: 3,
  backlogStop: 50,
  lowAccuracy: 0.7,
  lightWeeklyLimit: 2,
  defaultNewLimit: 6,
  // 英语 8、Java/AI 主线 6；其余学科走 defaultNewLimit。
  newLimits: { english: 8, java: 6, ai: 6 },
}

export function resolveConfig(config?: Partial<ScheduleConfig>): ScheduleConfig {
  return {
    ...DEFAULT_SCHEDULE_CONFIG,
    ...config,
    newLimits: { ...DEFAULT_SCHEDULE_CONFIG.newLimits, ...(config?.newLimits ?? {}) },
  }
}

export interface ScheduleInput {
  now: number
  subjects: ScheduleSubject[]
  dueCards: DueCard[]
  newCards: NewCard[]
  accuracy?: SubjectAccuracy[]
  /** light 科本周已排次数（不含今天将要排的这次） */
  lightUsedThisWeek?: Record<string, number>
  /** 今天已复习张数 */
  reviewedToday?: number
  /** 本周有学习的天数 */
  weekDays?: number
  config?: Partial<ScheduleConfig>
}

export interface ScheduledReview {
  card: DueCard
  /** 逾期天数（今天到期的为 0） */
  overdueDays: number
}

export interface ScheduledNewCard {
  card: NewCard
  subject: string
  /** 该科今天的新卡上限（已减半时为减半后值） */
  limit: number
  /** 是否因近 7 天正确率 <70% 而减半 */
  halved: boolean
}

export interface DaySummary {
  dueToday: number
  reviewed: number
  weekDays: number
}

export interface DaySchedule {
  /** 到期复习，按逾期天数降序（最逾期的在前），已截到 dailyReviewLimit */
  reviews: ScheduledReview[]
  /** 每科新卡（受阶段挑选、上限、减半、积压停新卡约束） */
  newCards: ScheduledNewCard[]
  /** 被挑中排新卡的学科 id */
  subjects: string[]
  /** 今天到期（未截断）总数 */
  dueTotal: number
  /** 到期积压（= dueTotal，project 不计） */
  backlog: number
  /** 是否因积压 > backlogStop 停掉新卡 */
  stoppedNewCards: boolean
  /** 是否有学科的复习被日上限截断 */
  reviewLimitHit: boolean
  summary: DaySummary
}

/** 近 7 天正确率；没作答返回 null。 */
export function accuracyOf(stat: SubjectAccuracy | undefined): number | null {
  if (!stat || stat.attempts <= 0) return null
  return stat.correct / stat.attempts
}

/** 弱项系数：显式值优先，否则正确率低于阈值给 1.5，其余 1。 */
export function weaknessOf(
  subject: ScheduleSubject,
  accuracy: number | null,
  threshold: number
): number {
  if (typeof subject.weakness === 'number' && Number.isFinite(subject.weakness)) {
    return subject.weakness
  }
  return accuracy !== null && accuracy < threshold ? 1.5 : 1
}

/** 新卡减半（向下取整到不小于一半的整数，0 仍是 0）。 */
export function halveLimit(limit: number): number {
  return limit <= 0 ? 0 : Math.ceil(limit / 2)
}

/** 某科今天的新卡上限（未计减半）。 */
export function newLimitFor(subjectId: string, config: ScheduleConfig): number {
  const v = config.newLimits[subjectId]
  return typeof v === 'number' && Number.isFinite(v) ? v : config.defaultNewLimit
}

export function startOfDay(ts: number): number {
  const d = new Date(ts)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

/** 本周一 00:00 的时间戳。 */
export function startOfWeek(ts: number): number {
  const d = new Date(startOfDay(ts))
  const dow = (d.getDay() + 6) % 7 // 周一 = 0
  d.setDate(d.getDate() - dow)
  return d.getTime()
}

/** timestamps 落在 [本周一, now] 的不同自然日天数。 */
export function activeDayCount(timestamps: number[], now: number): number {
  const from = startOfWeek(now)
  const days = new Set<number>()
  for (const ts of timestamps) {
    if (typeof ts === 'number' && ts >= from && ts <= now) days.add(startOfDay(ts))
  }
  return days.size
}

/**
 * 按课程表排今天的队。纯函数：同样输入必得同样输出。
 */
export function buildDaySchedule(input: ScheduleInput): DaySchedule {
  const config = resolveConfig(input.config)
  const now = input.now
  const accuracyMap = new Map<string, SubjectAccuracy>()
  for (const a of input.accuracy ?? []) accuracyMap.set(a.subject, a)

  // 1) 到期复习先行：project 不进队列，按逾期天数排序，截到日上限。
  const dueAll = input.dueCards
    .filter(c => c.type !== 'project' && c.due <= now)
    .sort((a, b) => a.due - b.due || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
  const dueTotal = dueAll.length
  const kept = dueAll.slice(0, config.dailyReviewLimit)
  const reviews: ScheduledReview[] = kept.map(card => ({
    card,
    overdueDays: Math.max(0, Math.floor((now - card.due) / DAY)),
  }))
  const reviewLimitHit = dueTotal > config.dailyReviewLimit

  // 2) 积压 >50 当天不出新卡。
  const stoppedNewCards = dueTotal > config.backlogStop

  return assemble(input, config, reviews, reviewLimitHit, stoppedNewCards, dueTotal, accuracyMap)
}

function assemble(
  input: ScheduleInput,
  config: ScheduleConfig,
  reviews: ScheduledReview[],
  reviewLimitHit: boolean,
  stoppedNewCards: boolean,
  dueTotal: number,
  accuracyMap: Map<string, SubjectAccuracy>
): DaySchedule {
  const scheduledNew: ScheduledNewCard[] = []
  const chosenSubjects: string[] = []

  if (!stoppedNewCards) {
    const lightUsed = input.lightUsedThisWeek ?? {}
    const scored = input.subjects
      .filter(s => s.stage !== 'project')
      .filter(s => input.newCards.some(c => c.subject === s.id && c.type !== 'project'))
      .filter(s => !(s.stage === 'light' && (lightUsed[s.id] ?? 0) >= config.lightWeeklyLimit))
      .map(s => ({
        subject: s,
        score:
          STAGE_WEIGHT[s.stage] *
          weaknessOf(s, accuracyOf(accuracyMap.get(s.id)), config.lowAccuracy),
      }))
      .sort((a, b) => b.score - a.score || (a.subject.id < b.subject.id ? -1 : 1))

    for (const { subject } of scored.slice(0, config.maxNewSubjects)) {
      const acc = accuracyOf(accuracyMap.get(subject.id))
      const halved = acc !== null && acc < config.lowAccuracy
      const base = newLimitFor(subject.id, config)
      const limit = halved ? halveLimit(base) : base
      chosenSubjects.push(subject.id)
      const cards = input.newCards
        .filter(c => c.subject === subject.id && c.type !== 'project')
        .slice(0, limit)
      for (const card of cards) {
        scheduledNew.push({ card, subject: subject.id, limit, halved })
      }
    }
  }

  return {
    reviews,
    newCards: scheduledNew,
    subjects: chosenSubjects,
    dueTotal,
    backlog: dueTotal,
    stoppedNewCards,
    reviewLimitHit,
    summary: {
      dueToday: dueTotal,
      reviewed: input.reviewedToday ?? 0,
      weekDays: input.weekDays ?? 0,
    },
  }
}

/** 完成页文案：只显示到期 / 已复习 / 本周天数，不做倒计时 / 连续天数。 */
export function formatDaySummary(summary: DaySummary): string {
  return `今天到期${summary.dueToday}、已复习${summary.reviewed}、本周${summary.weekDays}天`
}
