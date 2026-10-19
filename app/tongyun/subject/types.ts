// tongyun: 多学科内容模型 —— 学科 / 级别 / 单元 / 卡片。
// 兼容 java-v0.1.json、ai-v0.1.json：新增字段全部可选，旧题库原样可加载。

export type ItemType = 'code' | 'term' | 'concept' | 'choice' | 'oral' | 'project'

/** 判分方式：auto = 程序判；self = 自评 */
export type Grading = 'auto' | 'self'

/** 自评三档：会 / 半会 / 不会 */
export type SelfAssessment = 'self_ok' | 'self_partial' | 'self_fail'

export interface Point {
  id: string
  title: string
  prereq: string[]
  /** 级别，可选（旧题库可能没有） */
  level?: number
  /** 单元，可选 */
  unit?: string
  /** 知识地图挂点；null / 缺省表示「待挂」，照常排课但不计地图进度 */
  map_point?: string | null
  /** 关联的其他挂点，可选 */
  refs?: string[]
}

export interface Card {
  id: string
  point_id: string
  level: number
  type: ItemType
  prompt: string
  answer: string
  /** term / code / concept 的可接受答案（choice / oral / project 可为空） */
  accept?: string[]
  explain?: string
  /** code 题的参考代码 */
  code?: string
  tags?: string[]
  /** choice 选项（>=3，answer 必须在其中），自动判分 */
  options?: string[]
  /** oral / project 的评分要点，3–5 条，配合自评 */
  rubric?: string[]
  grading?: Grading
  /** 删卡只标 retired，不改 id */
  retired?: boolean
}

export interface QuestionBank {
  subject: string
  version: string
  points: Point[]
  items: Card[]
}

export interface SubjectMeta {
  id: string
  title: string
  /** 排课权重：主线 / 维持 / 轻量 */
  stage?: 'main' | 'maintain' | 'light'
  /** 内容文件（相对 content/），元数据用 */
  file: string
}

export interface Subject extends SubjectMeta {
  load(): Promise<QuestionBank>
}

/** 练习层进度（localStorage）；与内容模型分离 */
export interface SubjectItemStat {
  right: number
  wrong: number
  last: number
  /** 当前间隔档 0–4，对应 1/3/7/14/30 天 */
  box: number
  /** 下次到期（毫秒） */
  due: number
  first: number
}

export interface SubjectSessionPlan {
  items: Card[]
  dueTotal: number
  newTotal: number
}

/** 旧名别名，练习组件仍可用 */
export type KnowledgePoint = Point
export type QuestionItem = Card
export type QuestionType = ItemType
