import { POINT_STATES, type SubjectMap } from './learn-board-api'
export * from './learn-board-recommend'

export const JAVA_SUBJECT_ID = 'java-fde'

export interface BoardSubject {
  id: string
  title: string
}

export type SubjectSlot = 'java' | 'english' | 'other'

export function subjectSlot(sub: { id?: string | null; title?: string | null }): SubjectSlot {
  const id = String(sub.id || '')
    .trim()
    .toLowerCase()
  const title = String(sub.title || '').trim()
  const javaId = id === JAVA_SUBJECT_ID || id === 'java' || id.startsWith('java-') || id.startsWith('java_')
  // 「Java」「Java 基础」算 Java；「JavaScript」不算
  const javaTitle = /^java(?![a-z0-9])/i.test(title)
  if (javaId || javaTitle) {
    return 'java'
  }
  if (
    id === 'en' ||
    id === 'english' ||
    id === 'en-fde' ||
    id === 'english-fde' ||
    id.startsWith('en-') ||
    id.startsWith('english') ||
    title.includes('英语') ||
    /\benglish\b/i.test(title)
  ) {
    return 'english'
  }
  return 'other'
}

export function boardSubjectLabel(sub: { id?: string | null; title?: string | null }): string {
  const slot = subjectSlot(sub)
  if (slot === 'java') return 'Java'
  if (slot === 'english') return '英语'
  const title = String(sub.title || '').trim()
  return title || String(sub.id || '')
}

export function resolveBoardSubjects<T extends BoardSubject>(
  subjects: T[]
): {
  ordered: T[]
  java: T | null
  english: T | null
} {
  const list = subjects || []
  const java = list.find(s => subjectSlot(s) === 'java') || null
  let english = list.find(s => s !== java && subjectSlot(s) === 'english') || null
  const others = list.filter(s => s !== java && s !== english)
  // 只有 Java 和另一科时，另一科就当英语，避免看板看起来只有一科
  if (!english && java && others.length === 1) {
    english = others[0]
  }
  const rest = list.filter(s => s !== java && s !== english)
  const ordered = [java, english, ...rest].filter((s): s is T => s != null)
  return { ordered, java, english }
}

export interface MapStatusSummary {
  totalStages: number
  passedStages: number
  currentOrd: number | null
  currentTitle: string | null
  allPassed: boolean
  totalPoints: number
  masteredPoints: number
  counts: { key: string; label: string; color: string; count: number }[]
}

export function summarizeMap(map: SubjectMap | null | undefined): MapStatusSummary {
  const stages = (map?.stages || []).slice().sort((a, b) => (a.ord ?? 0) - (b.ord ?? 0))
  const passedStages = stages.filter(s => s.passed).length
  const current = stages.find(s => !s.passed) || null
  const countsMap: Record<string, number> = {}
  let totalPoints = 0
  for (const st of stages) {
    for (const p of st.points || []) {
      totalPoints += 1
      const key = p.stats?.state || 'available'
      countsMap[key] = (countsMap[key] || 0) + 1
    }
  }
  return {
    totalStages: stages.length,
    passedStages,
    currentOrd: current ? current.ord : null,
    currentTitle: current ? current.title : null,
    allPassed: stages.length > 0 && passedStages === stages.length,
    totalPoints,
    masteredPoints: countsMap.mastered || 0,
    counts: POINT_STATES.map(s => ({
      key: s.key,
      label: s.label,
      color: s.color,
      count: countsMap[s.key] || 0,
    })),
  }
}

export function mapStatusLine(summary: MapStatusSummary): string {
  if (summary.totalStages === 0) return '这科还没有阶段'
  if (summary.allPassed) {
    return `地图已全部通过 · ${summary.passedStages} / ${summary.totalStages} 阶段`
  }
  const title = summary.currentTitle || '未命名阶段'
  return `第 ${summary.currentOrd} 阶段 · ${title}`
}

export function mapProgressLine(summary: MapStatusSummary): string {
  if (summary.totalStages === 0) return '还没有知识点'
  const pass = summary.allPassed ? '全部阶段已通过' : `已通过 ${summary.passedStages} / ${summary.totalStages} 阶段`
  return `${pass} · 掌握 ${summary.masteredPoints} / 共 ${summary.totalPoints}`
}
