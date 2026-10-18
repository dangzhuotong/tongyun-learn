// tongyun: 当前选中学科状态管理（english / java / ai / fde / web / writing / ip / tools）

export type ActiveSubject =
  | 'english'
  | 'java'
  | 'ai'
  | 'fde'
  | 'web'
  | 'writing'
  | 'ip'
  | 'tools'

const KEY = 'tongyun-active-subject'

export const VALID_SUBJECTS = new Set<string>([
  'english',
  'java',
  'ai',
  'fde',
  'web',
  'writing',
  'ip',
  'tools',
])

export function getActiveSubject(): ActiveSubject {
  if (typeof localStorage === 'undefined') return 'english'
  try {
    const raw = (localStorage.getItem(KEY) || '').toLowerCase()
    if (VALID_SUBJECTS.has(raw)) return raw as ActiveSubject
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
  fde: 'FDE 客户沟通',
  web: '够用就行的前端与部署',
  writing: '技术写作与自媒体',
  ip: '个人 IP 与作品集',
  tools: '效率工具',
}
