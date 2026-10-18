// tongyun: 当前选中学科状态管理（english / java / ai）

export type ActiveSubject = 'english' | 'java' | 'ai'

const KEY = 'tongyun-active-subject'

export function getActiveSubject(): ActiveSubject {
  if (typeof localStorage === 'undefined') return 'english'
  try {
    const raw = (localStorage.getItem(KEY) || '').toLowerCase()
    if (raw === 'java' || raw === 'ai') return raw
  } catch {}
  return 'english'
}

export function setActiveSubject(subject: ActiveSubject): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(KEY, subject)
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('tongyun-subject-changed', { detail: subject }))
    }
  } catch {}
}

export const SUBJECT_TITLES: Record<ActiveSubject, string> = {
  english: '英语',
  java: 'Java',
  ai: 'AI',
}
