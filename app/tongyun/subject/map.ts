// tongyun: 知识地图进度 —— 只统计挂了 map_point 的点。
// map_point 缺省或为 null 表示「待挂」：照常排课，但不计入地图进度。

import type { Point, QuestionBank } from './types'

/** 点是否已挂到知识地图（map_point 为非空字符串）。 */
export function isAttachedPoint(p: Point): boolean {
  return typeof p.map_point === 'string' && p.map_point.trim() !== ''
}

/** 已挂到地图的点。 */
export function attachedPoints(bank: QuestionBank): Point[] {
  return bank.points.filter(isAttachedPoint)
}

/** 「待挂」点：map_point 缺省或 null。 */
export function pendingPoints(bank: QuestionBank): Point[] {
  return bank.points.filter(p => !isAttachedPoint(p))
}

export interface MapProgress {
  /** 已挂点数量，地图进度分母（不含待挂） */
  attached: number
  /** 待挂点数量，不计入地图进度 */
  pending: number
  total: number
}

/** 地图进度只用已挂点；待挂点不参与。 */
export function mapProgress(bank: QuestionBank): MapProgress {
  const attached = attachedPoints(bank).length
  return { attached, pending: bank.points.length - attached, total: bank.points.length }
}
