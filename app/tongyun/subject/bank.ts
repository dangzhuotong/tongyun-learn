// tongyun: 题库按学科动态 import —— 每个 load 都是 () => import(...)，
// 打包时切成独立 chunk，layout / 首页的主包不会包含题库内容。
// 注意：不要建把 bank 再全量导出的桶文件，否则会把题库拉回主包。

import { parseBank } from './parse'
import type { QuestionBank } from './types'

const LOADERS = {
  java: () => import('./content/java-v0.1.json').then(m => m.default ?? m),
  ai: () => import('./content/ai-v0.1.json').then(m => m.default ?? m),
} as const

/** 学科 id 的联合类型，由题库注册表推导 */
export type SubjectType = keyof typeof LOADERS

export const BANK_IDS = Object.keys(LOADERS) as SubjectType[]

export function hasBank(id: string): id is SubjectType {
  return Object.prototype.hasOwnProperty.call(LOADERS, id)
}

/**
 * 加载某学科题库。未知学科直接抛错，不静默回落到 Java。
 */
export async function loadBank(id: string): Promise<QuestionBank> {
  if (!hasBank(id)) throw new Error(`未知学科：${id}`)
  const raw = await LOADERS[id]()
  return parseBank(raw, id)
}
