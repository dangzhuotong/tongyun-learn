// tongyun: 本地练习队列。用阿学定制词表（L1–L5），先敲词再敲例句；不依赖学习服务，敲击只本地判分。
import type { PracticeStep, TodayQueue } from './types'
import { LEVELS, getLevel, loadWordlist, pickRound, type WordEntry } from './wordlist'

export function levelTitle(level: number): string {
  return LEVELS.find(l => l.level === level)?.title || `L${level}`
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
  }
  const steps: PracticeStep[] = [{ ...base, id: `l${w.level}-${i}-A`, stage: 'A', sentence: '', promptZh: w.meaning || '' }]
  if (w.example) {
    steps.push({ ...base, id: `l${w.level}-${i}-B`, stage: 'B', sentence: w.example, promptZh: w.example_zh || w.meaning || '' })
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
