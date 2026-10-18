// tongyun: 学科敲字练习类型定义（Java / AI 等）

export type SubjectType = 'java' | 'ai' | 'english'

export interface KnowledgePoint {
  id: string
  title: string
  prereq: string[]
}

export type QuestionType = 'concept' | 'term' | 'code' | string

export interface QuestionItem {
  id: string
  point_id: string
  level: number
  type: QuestionType
  prompt: string
  answer: string
  accept?: string[]
  explain: string
  code?: string
  tags?: string[]
}

export interface QuestionBank {
  subject: string
  version: string
  points: KnowledgePoint[]
  items: QuestionItem[]
}

export interface SubjectItemStat {
  right: number
  wrong: number
  last: number
  /** 当前所在间隔档 0–4，对应 1/3/7/14/30 天 */
  box: number
  /** 下次到期时间（毫秒时间戳） */
  due: number
  /** 首次作答时间 */
  first: number
}

export interface SubjectSessionPlan {
  items: QuestionItem[]
  dueTotal: number
  newTotal: number
}
