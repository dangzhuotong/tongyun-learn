// tongyun: 多学科课程表排课类型定义

export type SubjectStage = 'main' | 'maintain' | 'light'

export interface SubjectConfig {
  id: string
  name?: string
  stage: SubjectStage
  /** 7 天正确率，可传 0-1（如 0.69）或 0-100（如 69） */
  accuracy7d?: number
  /** 弱项系数，若不传则基于 accuracy7d 计算（1 - accuracy）或默认为 1 */
  weakness?: number
  /** 本周已排/学该学科新卡次数（light 学科每周最多 1-2 次） */
  trainedThisWeek?: number
  /** 自定义该学科每日新卡上限（若不传则按规则配置默认上限） */
  dailyNewCap?: number
  /** light 学科每周上限次数，默认 2（规则：<= 1-2x/week） */
  maxLightTimesPerWeek?: number
}

export interface CurriculumCard {
  id: string
  subject: string
  type?: string
  isProject?: boolean
  tags?: string[]
  due?: number
  daysOverdue?: number
  isReview?: boolean
  prompt?: string
  answer?: string
  explain?: string
  [key: string]: any
}

export interface SchedulerInput {
  subjects: SubjectConfig[]
  reviews?: CurriculumCard[]
  newCards?: Record<string, CurriculumCard[]> | CurriculumCard[]
  /** 逾期积压数，若不传则根据 reviews 中到期卡片数自动计算 */
  overdueBacklog?: number
  now?: number
  dailyReviewCap?: number
  minNewSubjects?: number
  maxNewSubjects?: number
  /** 本周已学习天数 */
  trainedDatesThisWeek?: number
}

export interface SchedulerResult {
  items: CurriculumCard[]
  reviewItems: CurriculumCard[]
  newItems: CurriculumCard[]
  dueTotal: number
  reviewedTotal: number
  weekDays: number
  selectedSubjects: string[]
  overdueBacklog: number
  newCardsBlockedByBacklog: boolean
  subjectAllocations: Record<string, number>
}
