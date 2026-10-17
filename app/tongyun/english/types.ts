// tongyun: 英语手敲 · 和 tongyun-learn 对齐的前端形状

export interface ExampleLine {
  en: string
  zh: string
}

export type PracticeStage = 'A' | 'B'

export interface PracticeStep {
  id: string
  stage: PracticeStage
  /** 今日队列里的 card_id，原样交给 POST /v1/type */
  cardId: string | number | null
  wordId: string
  sentenceId: string
  word: string
  phonetic: string
  meaning: string
  audioUrl: string
  sentence: string
  promptZh: string
  unitTitle: string
  examples: ExampleLine[]
  /** tongyun: 本地词表的主动回忆卡：先看中文+场景拼英文，交卡后才揭示 */
  recall?: boolean
  /** 场景标签（词表 tag） */
  tag?: string
  /** 语气标注（俚语/缩写等） */
  tone?: string
  /** 音标备注（词表 phonetic_note），揭示页显示 */
  phoneticNote?: string
}

export interface TodayQueue {
  unitTitle: string
  /** 0–1；服务端没给则为 null，前端不自己估 */
  unitProgress: number | null
  suggestion: string
  items: PracticeStep[]
}

export interface CoachWeak {
  word: string
  tag: string
  detail: string
  count: number | null
}

export interface CoachPlanItem {
  title: string
  note: string
}

export interface CoachView {
  summary: string
  weak: CoachWeak[]
  plan: CoachPlanItem[]
}

/** POST /v1/type 的正文。多出来的字段不送，避免严格校验直接 422。 */
export interface TypeEventBody {
  card_id: string | number
  phase: PracticeStage
  typed: string
  duration_ms: number
}

export type EnFailKind = 'no_token' | 'bad_token' | 'not_found' | 'unreachable'

export interface EnResult<T> {
  ok: boolean
  data?: T
  kind?: EnFailKind
  message?: string
  status: number
}
