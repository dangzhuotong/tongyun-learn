// tongyun: 题库解析与校验。新增字段（level/unit/map_point/refs/options/rubric/retired）
// 全部可选；旧题库 java-v0.1.json / ai-v0.1.json 不改也能原样加载。

import type { Card, ItemType, Point, QuestionBank } from './types'

export const ITEM_TYPES: ItemType[] = ['code', 'term', 'concept', 'choice', 'oral', 'project']

export function isItemType(v: unknown): v is ItemType {
  return typeof v === 'string' && (ITEM_TYPES as string[]).includes(v)
}

/** oral / project 由自评判分 */
export function isSelfType(type: ItemType): boolean {
  return type === 'oral' || type === 'project'
}

function asString(v: unknown): string | undefined {
  return typeof v === 'string' ? v : undefined
}

function asStringArray(v: unknown): string[] | undefined {
  if (!Array.isArray(v)) return undefined
  return v.filter((x): x is string => typeof x === 'string')
}

function asNumber(v: unknown): number | undefined {
  return typeof v === 'number' && Number.isFinite(v) ? v : undefined
}

function parsePoint(raw: unknown): Point {
  const r = (raw ?? {}) as Record<string, unknown>
  const id = asString(r.id)
  if (!id) throw new Error('点缺少 id')
  const title = asString(r.title) ?? ''
  const prereq = asStringArray(r.prereq) ?? []
  const point: Point = { id, title, prereq }
  const level = asNumber(r.level)
  if (level !== undefined) point.level = level
  const unit = asString(r.unit)
  if (unit !== undefined) point.unit = unit
  // map_point 允许显式 null（「待挂」）；缺省则不加字段
  if ('map_point' in r) point.map_point = asString(r.map_point) ?? null
  const refs = asStringArray(r.refs)
  if (refs) point.refs = refs
  return point
}

function parseCard(raw: unknown): Card {
  const r = (raw ?? {}) as Record<string, unknown>
  const id = asString(r.id)
  if (!id) throw new Error('卡片缺少 id')
  const type = asString(r.type)
  if (!isItemType(type)) throw new Error(`卡片 ${id} 的 type 不合法：${String(type)}`)
  const pointId = asString(r.point_id)
  if (!pointId) throw new Error(`卡片 ${id} 缺少 point_id`)
  const card: Card = {
    id,
    point_id: pointId,
    level: asNumber(r.level) ?? 0,
    type,
    prompt: asString(r.prompt) ?? '',
    answer: asString(r.answer) ?? '',
  }
  const accept = asStringArray(r.accept)
  if (accept) card.accept = accept
  const explain = asString(r.explain)
  if (explain !== undefined) card.explain = explain
  const code = asString(r.code)
  if (code !== undefined) card.code = code
  const tags = asStringArray(r.tags)
  if (tags) card.tags = tags
  const options = asStringArray(r.options)
  if (options) card.options = options
  const rubric = asStringArray(r.rubric)
  if (rubric) card.rubric = rubric
  const grading = asString(r.grading)
  if (grading === 'auto' || grading === 'self') card.grading = grading
  if (r.retired === true) card.retired = true
  return card
}

export interface BankIssue {
  path: string
  message: string
}

/** 软校验：返回问题清单，不抛错。choice 选项、rubric 条数、point_id 引用等。 */
export function validateBank(bank: QuestionBank): BankIssue[] {
  const issues: BankIssue[] = []
  const pointIds = new Set(bank.points.map(p => p.id))
  for (const p of bank.points) {
    for (const q of p.prereq) {
      if (!pointIds.has(q)) issues.push({ path: `point:${p.id}`, message: `prereq 不存在：${q}` })
    }
  }
  const seen = new Set<string>()
  for (const c of bank.items) {
    if (seen.has(c.id)) issues.push({ path: `card:${c.id}`, message: '卡片 id 重复' })
    seen.add(c.id)
    if (!pointIds.has(c.point_id)) {
      issues.push({ path: `card:${c.id}`, message: `point_id 不存在：${c.point_id}` })
    }
    if (c.type === 'choice') {
      const options = c.options ?? []
      if (options.length < 3) issues.push({ path: `card:${c.id}`, message: 'choice 选项少于 3 个' })
      if (new Set(options).size !== options.length) issues.push({ path: `card:${c.id}`, message: 'choice 选项有重复' })
      if (!options.includes(c.answer)) issues.push({ path: `card:${c.id}`, message: 'choice 答案不在选项里' })
    }
    if (isSelfType(c.type)) {
      const rubric = c.rubric ?? []
      if (rubric.length < 3 || rubric.length > 5) {
        issues.push({ path: `card:${c.id}`, message: `${c.type} rubric 需要 3–5 条` })
      }
    }
  }
  return issues
}

/**
 * 解析题库。expectedSubject 传学科 id 时校验 subject 一致（防错文件）。
 * 结构错误直接抛错；可选字段缺失都按兼容处理。
 */
export function parseBank(raw: unknown, expectedSubject?: string): QuestionBank {
  if (!raw || typeof raw !== 'object') throw new Error('题库不是对象')
  const r = raw as Record<string, unknown>
  const subject = asString(r.subject)
  if (!subject) throw new Error('题库缺少 subject')
  if (expectedSubject && subject !== expectedSubject) {
    throw new Error(`题库学科不匹配：期望 ${expectedSubject}，实际 ${subject}`)
  }
  const points = Array.isArray(r.points) ? r.points.map(parsePoint) : []
  const items = Array.isArray(r.items) ? r.items.map(parseCard) : []
  const bank: QuestionBank = { subject, version: asString(r.version) ?? '', points, items }
  const pointIds = new Set(points.map(p => p.id))
  for (const c of items) {
    if (!pointIds.has(c.point_id)) throw new Error(`卡片 ${c.id} 的 point_id 不存在：${c.point_id}`)
  }
  return bank
}

/** 未退役的卡片（删卡标 retired，id 不改） */
export function activeCards(bank: QuestionBank): Card[] {
  return bank.items.filter(c => !c.retired)
}
