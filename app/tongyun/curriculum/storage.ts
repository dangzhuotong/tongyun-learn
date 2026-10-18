// tongyun: 本周学习天数与课程表配置存储
import type { SubjectConfig } from './types'

const STORAGE_KEY_TRAINED_DATES = 'tongyun-curriculum-trained-dates-v1'
const STORAGE_KEY_SUBJECT_CONFIGS = 'tongyun-curriculum-subjects-v1'

function getDayString(timestamp: number): string {
  const d = new Date(timestamp)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const date = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${date}`
}

/**
 * 获取当前周的起始和结束时间（周一至周日）
 */
function getWeekRange(now = Date.now()): { startStr: string; endStr: string } {
  const d = new Date(now)
  const day = d.getDay()
  // 周日为 0，将其转换为 7
  const diffToMonday = (day === 0 ? 7 : day) - 1
  const monday = new Date(d)
  monday.setDate(d.getDate() - diffToMonday)
  monday.setHours(0, 0, 0, 0)

  const sunday = new Date(monday)
  sunday.setDate(monday.getDate() + 6)
  sunday.setHours(23, 59, 59, 999)

  return {
    startStr: getDayString(monday.getTime()),
    endStr: getDayString(sunday.getTime()),
  }
}

export function recordTrainingDay(now = Date.now()): string[] {
  if (typeof localStorage === 'undefined') return []
  try {
    const today = getDayString(now)
    const raw = localStorage.getItem(STORAGE_KEY_TRAINED_DATES)
    const set = new Set<string>(raw ? JSON.parse(raw) : [])
    set.add(today)
    const arr = Array.from(set)
    localStorage.setItem(STORAGE_KEY_TRAINED_DATES, JSON.stringify(arr))
    return arr
  } catch {
    return []
  }
}

export function getWeekTrainedDaysCount(now = Date.now()): number {
  if (typeof localStorage === 'undefined') return 1
  try {
    const raw = localStorage.getItem(STORAGE_KEY_TRAINED_DATES)
    const dates: string[] = raw ? JSON.parse(raw) : []
    const { startStr, endStr } = getWeekRange(now)
    const weekDates = dates.filter(d => d >= startStr && d <= endStr)
    const today = getDayString(now)
    if (!weekDates.includes(today)) {
      weekDates.push(today)
    }
    return Math.max(1, weekDates.length)
  } catch {
    return 1
  }
}

export const DEFAULT_CURRICULUM_SUBJECTS: SubjectConfig[] = [
  { id: 'english', name: '英语', stage: 'main' },
  { id: 'java', name: 'Java', stage: 'main' },
  { id: 'ai', name: 'AI', stage: 'main' },
]

export function getCurriculumSubjects(): SubjectConfig[] {
  if (typeof localStorage === 'undefined') return DEFAULT_CURRICULUM_SUBJECTS
  try {
    const raw = localStorage.getItem(STORAGE_KEY_SUBJECT_CONFIGS)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) return parsed
    }
  } catch {}
  return DEFAULT_CURRICULUM_SUBJECTS
}

export function saveCurriculumSubjects(subjects: SubjectConfig[]): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY_SUBJECT_CONFIGS, JSON.stringify(subjects))
  } catch {}
}
