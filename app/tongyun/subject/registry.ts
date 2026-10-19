// tongyun: 学科注册表。SUBJECTS = [{ id, title, load(): Promise<QuestionBank> }]。
// SubjectType 由题库加载表推导；页面校验用 getSubject / requireSubject，
// 未知学科抛错，不静默回落到 Java。

import subjectsData from './subjects.json'
import { hasBank, loadBank, type SubjectType } from './bank'
import type { QuestionBank, Subject, SubjectMeta } from './types'

export type { SubjectType }

interface RawSubjects {
  version: number
  subjects: SubjectMeta[]
}

/** subjects.json 是内容元数据来源；只保留有题库加载器的学科。 */
export const SUBJECTS: Subject[] = (subjectsData as RawSubjects).subjects
  .filter(meta => hasBank(meta.id))
  .map(meta => ({
    id: meta.id,
    title: meta.title,
    stage: meta.stage,
    file: meta.file,
    load: (): Promise<QuestionBank> => loadBank(meta.id),
  }))

/** 注册表里全部学科 id */
export const SUBJECT_IDS: string[] = SUBJECTS.map(s => s.id)

/** 页面对学科参数做校验；未知学科抛错。 */
export function isSubjectType(id: string): id is SubjectType {
  return SUBJECTS.some(s => s.id === id)
}

export function getSubject(id: string): Subject {
  const s = SUBJECTS.find(x => x.id === id)
  if (!s) throw new Error(`未知学科：${id}`)
  return s
}

/** 页面参数校验：传进来必须是注册表里的学科，否则抛错。 */
export function requireSubject(id: string | undefined | null): Subject {
  if (!id) throw new Error('缺少学科')
  return getSubject(id)
}
