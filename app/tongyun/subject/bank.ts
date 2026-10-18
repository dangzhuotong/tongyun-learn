// tongyun: 题库加载（Java / AI / FDE / Web / Writing / IP / Tools 学科题库 v0.1，随包放在 content/）
import javaBankRaw from './content/java-v0.1.json'
import aiBankRaw from './content/ai-v0.1.json'
import fdeBankRaw from './content/fde-v0.1.json'
import webBankRaw from './content/web-v0.1.json'
import writingBankRaw from './content/writing-v0.1.json'
import ipBankRaw from './content/ip-v0.1.json'
import toolsBankRaw from './content/tools-v0.1.json'
import subjectsRaw from './content/subjects.json'
import type {
  KnowledgePoint,
  QuestionBank,
  QuestionItem,
  SubjectDefinition,
  SubjectItemStat,
  SubjectMapProgress,
} from './types'

export function parseQuestionBank(raw: any): QuestionBank {
  if (!raw || typeof raw !== 'object') {
    return { subject: '', version: '', points: [], items: [] }
  }
  const points: KnowledgePoint[] = Array.isArray(raw.points)
    ? raw.points.map((p: any) => ({
        id: String(p.id || ''),
        title: String(p.title || ''),
        prereq: Array.isArray(p.prereq) ? p.prereq.map(String) : [],
        level: p.level !== undefined ? Number(p.level) : undefined,
        unit: p.unit !== undefined && p.unit !== null ? String(p.unit) : undefined,
        map_point: p.map_point !== undefined ? (p.map_point ? String(p.map_point) : null) : null,
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
        options: Array.isArray(it.options) ? it.options.map(String) : undefined,
        rubric: Array.isArray(it.rubric) ? it.rubric.map(String) : undefined,
        grading: it.grading ? String(it.grading) : undefined,
      }))
    : []

  return {
    subject: String(raw.subject || ''),
    version: String(raw.version || ''),
    title: raw.title ? String(raw.title) : undefined,
    note: raw.note ? String(raw.note) : undefined,
    points,
    items,
  }
}

export const SUBJECTS_REGISTRY: SubjectDefinition[] = Array.isArray(subjectsRaw)
  ? (subjectsRaw as SubjectDefinition[])
  : []

export const JAVA_BANK: QuestionBank = parseQuestionBank(javaBankRaw)
export const AI_BANK: QuestionBank = parseQuestionBank(aiBankRaw)
export const FDE_BANK: QuestionBank = parseQuestionBank(fdeBankRaw)
export const WEB_BANK: QuestionBank = parseQuestionBank(webBankRaw)
export const WRITING_BANK: QuestionBank = parseQuestionBank(writingBankRaw)
export const IP_BANK: QuestionBank = parseQuestionBank(ipBankRaw)
export const TOOLS_BANK: QuestionBank = parseQuestionBank(toolsBankRaw)

const BANK_MAP: Record<string, QuestionBank> = {
  java: JAVA_BANK,
  ai: AI_BANK,
  fde: FDE_BANK,
  web: WEB_BANK,
  writing: WRITING_BANK,
  ip: IP_BANK,
  tools: TOOLS_BANK,
}

export function getAllBanks(): Record<string, QuestionBank> {
  return { ...BANK_MAP }
}

export function getSubjectBank(subject: string): QuestionBank {
  const s = (subject || '').trim().toLowerCase()
  return BANK_MAP[s] || JAVA_BANK
}

export function getKnowledgePoint(bank: QuestionBank, pointId: string): KnowledgePoint | undefined {
  return bank.points.find(p => p.id === pointId)
}

/**
 * 判断知识点是否为「待挂」单元（map_point 为 null 或未关联到知识地图）
 */
export function isPendingMapPoint(point: KnowledgePoint): boolean {
  return !point.map_point
}

/**
 * 获取学科题库中已关联到知识地图的知识点（排除 map_point 为 null 的「待挂」单元）
 */
export function getMapPoints(bank: QuestionBank): KnowledgePoint[] {
  return bank.points.filter(p => Boolean(p.map_point))
}

/**
 * 获取学科题库中尚未挂入知识地图的「待挂」知识点
 */
export function getPendingMapPoints(bank: QuestionBank): KnowledgePoint[] {
  return bank.points.filter(p => !p.map_point)
}

/**
 * 计算学科知识地图进度：
 * 规则：map_point 为 null 的「待挂」点（如 ip P1、tools T1/T2、writing W1/W2）被严格排除在地图总点数和掌握数之外。
 */
export function calculateSubjectMapProgress(
  bank: QuestionBank,
  stats: Record<string, SubjectItemStat> = {}
): SubjectMapProgress {
  const mapPoints = getMapPoints(bank)
  const pendingPoints = getPendingMapPoints(bank)

  let masteredMapPoints = 0
  let learnedMapPoints = 0

  for (const pt of mapPoints) {
    const pointItems = bank.items.filter(it => it.point_id === pt.id)
    if (pointItems.length === 0) continue

    const hasLearned = pointItems.every(it => {
      const s = stats[it.id]
      return s && s.last > 0
    })
    const isMastered = pointItems.every(it => {
      const s = stats[it.id]
      return s && s.box >= 4
    })

    if (isMastered) masteredMapPoints++
    if (hasLearned) learnedMapPoints++
  }

  return {
    subject: bank.subject,
    totalMapPoints: mapPoints.length,
    masteredMapPoints,
    learnedMapPoints,
    pendingPointsCount: pendingPoints.length,
    mapPoints,
    pendingPoints,
  }
}
