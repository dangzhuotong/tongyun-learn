// tongyun: 今日队列 / 教练响应的薄适配。字段名略有差别时收成同一形状。
// 不补句子、不重排：服务端没把某项标成敲句，这里就只出敲词。

import type { CoachPlanItem, CoachView, CoachWeak, ExampleLine, PracticeStage, PracticeStep, TodayQueue } from './types'

function str(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

function readProgress(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  const scaled = value > 1 && value <= 100 ? value / 100 : value
  if (scaled < 0) return 0
  if (scaled > 1) return 1
  return scaled
}

function unwrap(raw: unknown): Record<string, any> {
  if (Array.isArray(raw)) return { items: raw }
  if (!raw || typeof raw !== 'object') return {}
  const obj = raw as Record<string, any>
  if (Array.isArray(obj.data) && !Array.isArray(obj.items) && !Array.isArray(obj.queue)) {
    return { ...obj, items: obj.data }
  }
  if (obj.data && typeof obj.data === 'object' && !Array.isArray(obj.data)) {
    return { ...obj, ...obj.data }
  }
  return obj
}

function firstList(root: Record<string, any>, keys: string[]): any[] {
  for (const key of keys) {
    if (Array.isArray(root[key])) return root[key]
  }
  return []
}

type StageSignal = 'A' | 'B' | 'AB'

function normStage(value: unknown): PracticeStage | '' {
  const s = str(value).toLowerCase()
  if (['a', 'word', 'type_word', 'spell', '词', '敲词'].includes(s)) return 'A'
  if (['b', 'sentence', 'type_sentence', 'sent', '例句', '敲句'].includes(s)) return 'B'
  return ''
}

function sentenceFlag(item: Record<string, any>): boolean {
  return (
    item.include_sentence === true ||
    item.with_sentence === true ||
    item.type_sentence === true ||
    item.do_sentence === true
  )
}

function stageSignal(item: Record<string, any>): StageSignal {
  const list = item.stages ?? item.parts
  if (Array.isArray(list) && list.length) {
    let hasA = false
    let hasB = false
    for (const entry of list) {
      const stage = normStage(entry)
      if (stage === 'A') hasA = true
      if (stage === 'B') hasB = true
    }
    if (hasA && hasB) return 'AB'
    if (hasB) return 'B'
    if (hasA) return 'A'
  }
  const direct = normStage(item.stage ?? item.phase ?? item.mode ?? item.step ?? item.kind)
  if (direct === 'B') return 'B'
  if (direct === 'A') return sentenceFlag(item) ? 'AB' : 'A'
  if (sentenceFlag(item)) return 'AB'
  if (collectSentences(item).length && !wordText(item)) return 'B'
  return 'A'
}

function wordText(item: Record<string, any>): string {
  return str(item.word ?? item.spelling ?? item.headword ?? item.lemma ?? item.answer)
}

/** 只认队列里的 card_id。数字字符串收成整数，方便后端按 int 收。 */
export function asCardId(value: unknown): string | number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value !== 'string') return null
  const text = value.trim()
  if (!text) return null
  if (/^[0-9]+$/.test(text)) {
    const num = Number(text)
    if (Number.isSafeInteger(num)) return num
  }
  return text
}

function cardIdOf(item: Record<string, any>): string | number | null {
  const direct = asCardId(item.card_id ?? item.cardId)
  if (direct !== null) return direct
  const card = item.card
  if (card && typeof card === 'object') return asCardId(card.card_id ?? card.cardId ?? card.id)
  return null
}

function meaningOf(item: Record<string, any>): string {
  const direct = str(item.meaning ?? item.cn ?? item.gloss ?? item.definition ?? item.translation_cn)
  if (direct) return direct
  if (Array.isArray(item.trans)) {
    const joined = item.trans.map((entry: any) => str(entry?.cn ?? entry?.meaning ?? entry)).filter(Boolean)
    if (joined.length) return joined.join('；')
  }
  if (Array.isArray(item.meanings)) {
    const joined = item.meanings
      .map((entry: any) => (typeof entry === 'string' ? entry.trim() : str(entry?.cn ?? entry?.meaning)))
      .filter(Boolean)
    if (joined.length) return joined.join('；')
  }
  if (!item.sentence && !item.sentence_zh && !item.prompt_zh) return str(item.translation)
  return ''
}

function phoneticOf(item: Record<string, any>): string {
  return str(item.phonetic ?? item.ipa ?? item.usphone ?? item.ukphone ?? item.pronunciation)
}

function audioOf(item: Record<string, any>): string {
  return str(item.audio ?? item.audio_url ?? item.audioUrl)
}

interface SentenceDraft {
  en: string
  zh: string
  id: string
}

function pairFrom(value: any, fallbackZh = '', fallbackId = ''): SentenceDraft | null {
  if (typeof value === 'string') {
    const en = value.trim()
    if (!en) return null
    return { en, zh: fallbackZh, id: fallbackId }
  }
  if (!value || typeof value !== 'object') return null
  const en = str(value.en ?? value.sentence ?? value.text ?? value.english)
  if (!en) return null
  return {
    en,
    zh: str(value.zh ?? value.cn ?? value.translation ?? value.prompt) || fallbackZh,
    id: str(value.id ?? value.sentence_id ?? value.sentenceId) || fallbackId,
  }
}

function promptOf(item: Record<string, any>): string {
  return str(item.sentence_zh ?? item.prompt_zh ?? item.prompt ?? item.cn_sentence)
}

function sentenceSources(item: Record<string, any>): any[] {
  const payload = item.payload && typeof item.payload === 'object' ? item.payload : {}
  if (Array.isArray(item.sentences)) return item.sentences
  if (Array.isArray(payload.sentences)) return payload.sentences
  return []
}

function collectSentences(item: Record<string, any>): SentenceDraft[] {
  const fallbackZh = promptOf(item)
  const fallbackId = str(item.sentence_id ?? item.sentenceId)
  const list: SentenceDraft[] = []
  for (const entry of sentenceSources(item)) {
    const pair = pairFrom(entry, fallbackZh, fallbackId)
    if (pair) list.push(pair)
  }
  if (list.length) return list
  const single = pairFrom(item.sentence ?? item.en_sentence ?? item.english ?? item.target, fallbackZh, fallbackId)
  if (single) {
    if (!single.zh) single.zh = fallbackZh
    return [single]
  }
  return []
}

function exampleSources(item: Record<string, any>): any[] {
  const payload = item.payload && typeof item.payload === 'object' ? item.payload : {}
  if (Array.isArray(item.examples)) return item.examples
  if (Array.isArray(payload.examples)) return payload.examples
  return []
}

function examplesOf(item: Record<string, any>, sentences: SentenceDraft[]): ExampleLine[] {
  const fromField = exampleSources(item)
    .map(entry => pairFrom(entry))
    .filter((entry): entry is SentenceDraft => Boolean(entry))
    .map(entry => ({ en: entry.en, zh: entry.zh }))
  if (fromField.length) return fromField.slice(0, 4)
  return sentences.slice(0, 4).map(entry => ({ en: entry.en, zh: entry.zh }))
}

function composeUnit(root: Record<string, any>, item?: Record<string, any>): { title: string; progress: number | null } {
  const unit = root.unit ?? root.current_unit ?? item?.unit
  let title = ''
  let progress = readProgress(root.unit_progress ?? root.progress)
  if (typeof unit === 'string') {
    title = unit.trim()
  } else if (unit && typeof unit === 'object') {
    title = str(unit.title ?? unit.name)
    const index = str(unit.index ?? unit.order ?? unit.ord ?? unit.no)
    progress = readProgress(unit.progress ?? unit.ratio ?? unit.percent) ?? progress
    if (!title && index) title = `单元 ${index}`
  }
  if (!title) title = str(root.unit_title ?? root.unitTitle ?? item?.unit_title ?? item?.unitTitle)
  const track = str(
    (unit && typeof unit === 'object' && (unit.track_title || unit.track)) || root.track_title || root.track
  )
  if (track && title && !title.includes(track)) title = `${track} · ${title}`
  else if (track && !title) title = track
  return { title, progress }
}

function stepId(
  item: Record<string, any>,
  stage: PracticeStage,
  index: number,
  sentenceId: string,
  sentenceOrd: number
): string {
  const base =
    str(item.id ?? item.item_id ?? item.step_id ?? item.word_id ?? item.wordId ?? item.card_id ?? item.cardId) ||
    `i${index}`
  if (stage === 'B') return `${base}:B:${index}:${sentenceId || sentenceOrd}`
  return `${base}:A:${index}`
}

function pushStep(
  out: PracticeStep[],
  item: Record<string, any>,
  stage: PracticeStage,
  index: number,
  unitTitle: string,
  sentence?: SentenceDraft,
  examples: ExampleLine[] = [],
  sentenceOrd = 0
): void {
  const word = wordText(item)
  const sentenceEn = sentence?.en || ''
  if (stage === 'A' && !word) return
  if (stage === 'B' && !sentenceEn) return
  const sentenceId = sentence?.id || (stage === 'B' ? str(item.sentence_id ?? item.sentenceId) : '')
  out.push({
    id: stepId(item, stage, index, sentenceId, sentenceOrd),
    stage,
    cardId: cardIdOf(item),
    wordId: str(item.word_id ?? item.wordId),
    sentenceId: stage === 'B' ? sentenceId : '',
    word,
    phonetic: phoneticOf(item),
    meaning: meaningOf(item),
    audioUrl: audioOf(item),
    sentence: stage === 'B' ? sentenceEn : '',
    promptZh: stage === 'B' ? sentence?.zh || promptOf(item) : '',
    unitTitle: str(item.unit_title ?? item.unitTitle) || unitTitle,
    examples: stage === 'A' ? examples : [],
  })
}

export function adaptToday(raw: unknown): TodayQueue {
  const root = unwrap(raw)
  const unit = composeUnit(root)
  const suggestion = str(
    root.suggestion ?? root.advice ?? root.coach_line ?? root.one_liner ?? root.summary ?? root.coach?.summary ?? root.coach?.suggestion
  )
  const source = firstList(root, ['items', 'queue', 'steps', 'tasks', 'cards', 'words'])
  const items: PracticeStep[] = []
  source.forEach((entry, index) => {
    if (!entry || typeof entry !== 'object') return
    const item = entry as Record<string, any>
    const signal = stageSignal(item)
    const sentences = collectSentences(item)
    const examples = examplesOf(item, sentences)
    const title = composeUnit(root, item).title || unit.title
    if (signal === 'B') {
      let rows = sentences
      if (!rows.length) {
        const answer = str(item.answer ?? item.en)
        if (answer) rows = [{ en: answer, zh: promptOf(item) || meaningOf(item), id: '' }]
      }
      rows.forEach((sentence, sentenceOrd) => pushStep(items, item, 'B', index, title, sentence, [], sentenceOrd))
      return
    }
    if (signal === 'AB') {
      pushStep(items, item, 'A', index, title, undefined, examples)
      sentences.forEach((sentence, sentenceOrd) =>
        pushStep(items, item, 'B', index, title, sentence, [], sentenceOrd)
      )
      return
    }
    pushStep(items, item, 'A', index, title, undefined, examples)
  })
  return {
    unitTitle: unit.title,
    unitProgress: unit.progress,
    suggestion,
    items,
  }
}

function weakOf(entry: any): CoachWeak | null {
  if (!entry || typeof entry !== 'object') {
    const word = str(entry)
    if (!word) return null
    return { word, tag: '', detail: '', count: null }
  }
  const word = str(entry.word ?? entry.headword ?? entry.spelling ?? entry.text)
  if (!word) return null
  const countRaw = entry.count ?? entry.times ?? entry.wrong_count
  const count = typeof countRaw === 'number' && Number.isFinite(countRaw) ? countRaw : null
  return {
    word,
    tag: str(entry.tag ?? entry.reason ?? entry.label ?? entry.kind),
    detail: str(entry.detail ?? entry.note ?? entry.explain ?? entry.error ?? entry.error_text),
    count,
  }
}

function planOf(entry: any): CoachPlanItem | null {
  if (typeof entry === 'string') {
    const title = entry.trim()
    return title ? { title, note: '' } : null
  }
  if (!entry || typeof entry !== 'object') return null
  const title = str(entry.title ?? entry.text ?? entry.action ?? entry.task ?? entry.word)
  if (!title) return null
  return {
    title,
    note: str(entry.note ?? entry.detail ?? entry.when ?? entry.explain),
  }
}

export function adaptCoach(raw: unknown): CoachView {
  const root = unwrap(raw)
  const summary = str(
    root.summary ?? root.suggestion ?? root.advice ?? root.one_liner ?? root.coach_line ?? root.headline
  )
  const weakList = firstList(root, ['weak_points', 'weaknesses', 'weak', 'nails', 'top_words', 'blockers'])
  const planList = firstList(root, ['plan', 'week_plan', 'weekly_plan', 'weekly', 'tomorrow'])
  let weak = weakList.map(weakOf).filter((entry): entry is CoachWeak => Boolean(entry))
  let plan = planList.map(planOf).filter((entry): entry is CoachPlanItem => Boolean(entry))
  if (!weak.length && !plan.length && Array.isArray(root.items)) {
    const sample = root.items[0]
    const looksLikePlan =
      typeof sample === 'string' || (sample && typeof sample === 'object' && (sample.title || sample.action || sample.task))
    if (looksLikePlan) plan = root.items.map(planOf).filter((entry): entry is CoachPlanItem => Boolean(entry))
    else weak = root.items.map(weakOf).filter((entry): entry is CoachWeak => Boolean(entry))
  }
  return { summary, weak, plan }
}
