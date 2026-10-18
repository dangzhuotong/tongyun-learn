// tongyun: 题库加载（Java / AI 学科题库，来源 docs/tasks/）
import javaBankRaw from '../../../docs/tasks/java-v0.1.json'
import aiBankRaw from '../../../docs/tasks/ai-v0.1.json'
import type { KnowledgePoint, QuestionBank, QuestionItem } from './types'

export function parseQuestionBank(raw: any): QuestionBank {
  if (!raw || typeof raw !== 'object') {
    return { subject: '', version: '', points: [], items: [] }
  }
  const points: KnowledgePoint[] = Array.isArray(raw.points)
    ? raw.points.map((p: any) => ({
        id: String(p.id || ''),
        title: String(p.title || ''),
        prereq: Array.isArray(p.prereq) ? p.prereq.map(String) : [],
      }))
    : []

  const items: QuestionItem[] = Array.isArray(raw.items)
    ? raw.items.map((it: any) => ({
        id: String(it.id || ''),
        point_id: String(it.point_id || ''),
        level: Number(it.level || 1),
        type: String(it.type || 'term'),
        prompt: String(it.prompt || ''),
        answer: String(it.answer || ''),
        accept: Array.isArray(it.accept) ? it.accept.map(String) : [],
        explain: String(it.explain || ''),
        code: it.code ? String(it.code) : undefined,
        tags: Array.isArray(it.tags) ? it.tags.map(String) : [],
      }))
    : []

  return {
    subject: String(raw.subject || ''),
    version: String(raw.version || ''),
    points,
    items,
  }
}

export const JAVA_BANK: QuestionBank = parseQuestionBank(javaBankRaw)
export const AI_BANK: QuestionBank = parseQuestionBank(aiBankRaw)

export function getSubjectBank(subject: string): QuestionBank {
  const s = (subject || '').trim().toLowerCase()
  if (s === 'ai') return AI_BANK
  return JAVA_BANK
}

export function getKnowledgePoint(bank: QuestionBank, pointId: string): KnowledgePoint | undefined {
  return bank.points.find(p => p.id === pointId)
}
