// tongyun: 当前学科。layout 只从这里取学科信息（不直接引 bank / 题库），
// 题库仍由 registry.load() 按需动态 import。

import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { SUBJECTS, getSubject, isSubjectType, type SubjectType } from './registry'
import type { Subject } from './types'

const STORAGE_KEY = 'tongyun-active-subject-v1'

function readStored(): SubjectType | null {
  try {
    if (typeof localStorage === 'undefined') return null
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw && isSubjectType(raw)) return raw
  } catch {}
  return null
}

function fallbackId(): SubjectType {
  const first = SUBJECTS[0]
  if (!first) throw new Error('学科注册表为空')
  return first.id as SubjectType
}

const activeId: Ref<SubjectType> = ref<SubjectType>(readStored() ?? fallbackId())

export interface UseActiveSubject {
  activeId: ComputedRef<SubjectType>
  active: ComputedRef<Subject>
  subjects: Subject[]
  setActiveSubject(id: string): SubjectType
}

/** 切换当前学科；未知学科抛错，不静默回落。 */
export function setActiveSubject(id: string): SubjectType {
  const subject = getSubject(id)
  const next = subject.id as SubjectType
  activeId.value = next
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, next)
  } catch {}
  return next
}

export function useActiveSubject(): UseActiveSubject {
  const active = computed<Subject>(() => getSubject(activeId.value))
  return {
    activeId: computed(() => activeId.value),
    active,
    subjects: SUBJECTS,
    setActiveSubject,
  }
}

/** 测试用：重置内存中的当前学科。 */
export function __resetActiveSubject(id?: SubjectType): void {
  activeId.value = id ?? fallbackId()
}
