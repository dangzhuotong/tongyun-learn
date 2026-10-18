// tongyun: 本地练习队列（阿学词表 v0.2）。主动回忆：先看中文+场景拼英文 → 揭示音标/例句 → 整句敲例句。
// 不依赖学习服务，敲击只本地判分。
import type { PracticeStep, TodayQueue } from './types'
import { LEVELS, TAG_LABEL, getLevel, loadWordlist, pickRound, toneOf, type WordEntry } from './wordlist'

export function levelTitle(level: number): string {
  return LEVELS.find(l => l.level === level)?.title || `L${level}`
}

/** 例句转成可手敲的一句：去掉引用行（> 开头）、emoji，破折号换成 -，合并空白 */
export function typeableSentence(example: string): string {
  return (example || '')
    .split('\n')
    .filter(line => !line.trim().startsWith('>'))
    .join(' ')
    .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/gu, '')
    .replace(/[—–]/g, '-')
    .replace(/[“”]/g, '"')
    .replace(/[’‘]/g, "'")
    .replace(/\s+/g, ' ')
    .trim()
}

export function entryToSteps(w: WordEntry, i: number): PracticeStep[] {
  const base = {
    cardId: null,
    wordId: w.word,
    sentenceId: '',
    word: w.word,
    phonetic: w.phonetic || '',
    meaning: w.meaning || '',
    audioUrl: '',
    unitTitle: levelTitle(w.level),
    examples: w.example ? [{ en: w.example, zh: w.example_zh || '' }] : [],
    recall: true,
    tag: TAG_LABEL[w.tag] || w.tag || '',
    tone: toneOf(w),
    phoneticNote: w.phonetic_note || '',
  }
  const steps: PracticeStep[] = [{ ...base, id: `l${w.level}-${i}-A`, stage: 'A', sentence: '', promptZh: w.meaning || '' }]
  const sentence = typeableSentence(w.example)
  if (sentence) {
    steps.push({ ...base, id: `l${w.level}-${i}-B`, stage: 'B', sentence, promptZh: w.example_zh || w.meaning || '' })
  }
  return steps
}

export function roundToQueue(words: WordEntry[], level: number): TodayQueue {
  return {
    unitTitle: levelTitle(level),
    unitProgress: null,
    suggestion: '',
    items: words.flatMap((w, i) => entryToSteps(w, i)),
  }
}

export async function buildLocalQueue(level = getLevel()): Promise<TodayQueue> {
  const list = await loadWordlist()
  return roundToQueue(pickRound(list, level), level)
}
