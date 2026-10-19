// tongyun: 唯一的当前学科存储（含英语）。顶栏 / 今日 / 练习共用同一 key，并广播 tongyun-subject-changed。
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { SUBJECTS, getSubject, isSubjectType, type SubjectType } from './registry'
import type { Subject } from './types'

export const STORAGE_KEY = 'tongyun-active-subject'
const LEGACY_KEY = 'tongyun-active-subject-v1'

/** 练习/今日/顶栏：英语或题库注册表里的 id */
export type ActiveSubject = 'english' | SubjectType

export interface UiSubject {
  id: ActiveSubject
  title: string
  /** 注册表学科才有；英语没有 load */
  stage?: Subject['stage']
  file?: string
  load?: Subject['load']
}

const ENGLISH: UiSubject = { id: 'english', title: '英语' }

/** 顶栏可选：英语 + 注册表学科 */
export const UI_SUBJECTS: UiSubject[] = [
  ENGLISH,
  ...SUBJECTS.map(s => ({
    id: s.id as ActiveSubject,
    title: s.title,
    stage: s.stage,
    file: s.file,
    load: s.load.bind(s),
  })),
]

function readStored(): ActiveSubject | null {
  try {
    if (typeof localStorage === 'undefined') return null
    const raw = (localStorage.getItem(STORAGE_KEY) || localStorage.getItem(LEGACY_KEY) || '').toLowerCase()
    if (raw === 'english') return 'english'
    if (raw && isSubjectType(raw)) return raw
  } catch {}
  return null
}

function writeStored(id: ActiveSubject): void {
  try {
    if (typeof localStorage === 'undefined') return
    localStorage.setItem(STORAGE_KEY, id)
    // 清理旧 key，避免双写分叉
    localStorage.removeItem(LEGACY_KEY)
  } catch {}
}

function emitChanged(id: ActiveSubject): void {
  try {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('tongyun-subject-changed', { detail: id }))
    }
  } catch {}
}

const activeId: Ref<ActiveSubject> = ref<ActiveSubject>(readStored() ?? 'english')

export function getActiveSubject(): ActiveSubject {
  return activeId.value
}

export function isBankSubject(subject: string): subject is SubjectType {
  return isSubjectType(subject)
}

function resolveUi(id: ActiveSubject): UiSubject {
  if (id === 'english') return ENGLISH
  const found = UI_SUBJECTS.find(s => s.id === id)
  if (found) return found
  // 注册表已知但 UI 列表尚未刷新时兜底
  const reg = getSubject(id)
  return { id: reg.id as ActiveSubject, title: reg.title, stage: reg.stage, file: reg.file, load: reg.load.bind(reg) }
}

/** 切换当前学科；未知学科抛错。英语合法。会写同一 key 并广播事件。 */
export function setActiveSubject(id: string): ActiveSubject {
  const next = id.toLowerCase()
  if (next === 'english') {
    activeId.value = 'english'
    writeStored('english')
    emitChanged('english')
    return 'english'
  }
  if (!isSubjectType(next)) throw new Error(`未知学科：${id}`)
  // 校验注册表存在
  getSubject(next)
  activeId.value = next
  writeStored(next)
  emitChanged(next)
  return next
}

export interface UseActiveSubject {
  activeId: ComputedRef<ActiveSubject>
  active: ComputedRef<UiSubject>
  subjects: UiSubject[]
  setActiveSubject(id: string): ActiveSubject
}

export function useActiveSubject(): UseActiveSubject {
  return {
    activeId: computed(() => activeId.value),
    active: computed(() => resolveUi(activeId.value)),
    subjects: UI_SUBJECTS,
    setActiveSubject,
  }
}

/** 测试用：重置内存中的当前学科。 */
export function __resetActiveSubject(id?: ActiveSubject): void {
  activeId.value = id ?? 'english'
}
