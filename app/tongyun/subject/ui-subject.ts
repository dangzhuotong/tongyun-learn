// tongyun: UI 层当前学科（含英语）。注册表学科会同步到 active-subject。
import { isSubjectType, type SubjectType } from './registry'
import { setActiveSubject as setRegistrySubject } from './active-subject'

const UI_KEY = 'tongyun-active-subject'

/** 练习/今日用的学科：英语或题库注册表里的 id */
export type ActiveSubject = 'english' | SubjectType

export function getActiveSubject(): ActiveSubject {
  if (typeof localStorage === 'undefined') return 'english'
  try {
    const raw = (localStorage.getItem(UI_KEY) || '').toLowerCase()
    if (raw === 'english') return 'english'
    if (raw && isSubjectType(raw)) return raw
  } catch {}
  return 'english'
}

export function setActiveSubject(subject: ActiveSubject): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(UI_KEY, subject)
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('tongyun-subject-changed', { detail: subject }))
    }
  } catch {}
  if (subject !== 'english' && isSubjectType(subject)) {
    try {
      setRegistrySubject(subject)
    } catch {}
  }
}

export function isBankSubject(subject: string): subject is SubjectType {
  return isSubjectType(subject)
}
