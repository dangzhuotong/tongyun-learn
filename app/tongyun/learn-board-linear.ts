// tongyun: 看板按线性单元课表往前推荐。当前单元里第一个还没学完的点，以及它后面的相邻点。
// 不看前置网，也不再使用「锁定」态：旧接口里的 locked 一律当成可学。

import type { MapPoint, MapStage, NextItem, SubjectMap } from './learn-board-api'

const VISIBLE_STATES = new Set(['available', 'learning', 'learned', 'mastered', 'rusty'])
const DONE_STATES = new Set(['learned', 'mastered'])

export function displayPointState(state?: string | null): string {
  if (!state || state === 'locked') return 'available'
  if (VISIBLE_STATES.has(state)) return state
  return 'available'
}

export function foldPointCounts(counts: Record<string, number> | null | undefined): Record<string, number> {
  const out: Record<string, number> = {}
  for (const [key, value] of Object.entries(counts || {})) {
    const folded = displayPointState(key)
    out[folded] = (out[folded] || 0) + (Number(value) || 0)
  }
  return out
}

interface LinearStop {
  point: MapPoint
  stage: MapStage
}

function orderedPoints(stage: MapStage): MapPoint[] {
  return [...(stage.points || [])]
    .map((point, index) => ({
      point,
      index,
      ord: typeof point.ord === 'number' ? point.ord : index,
    }))
    .sort((a, b) => a.ord - b.ord || a.index - b.index)
    .map(item => item.point)
}

export function linearCurriculum(map: SubjectMap | null | undefined): LinearStop[] {
  const stages = [...(map?.stages || [])].sort((a, b) => (a.ord ?? 0) - (b.ord ?? 0) || String(a.id).localeCompare(String(b.id)))
  const line: LinearStop[] = []
  for (const stage of stages) {
    for (const point of orderedPoints(stage)) line.push({ point, stage })
  }
  return line
}

function unfinished(point: MapPoint): boolean {
  return !DONE_STATES.has(displayPointState(point.stats?.state))
}

export function recommendUnitForward(map: SubjectMap, subjectId?: string, limit = 5): NextItem[] {
  const line = linearCurriculum(map)
  const start = line.findIndex(item => unfinished(item.point))
  if (start < 0 || limit <= 0) return []
  const currentStageId = line[start].stage.id
  const picked: NextItem[] = []
  for (let i = start; i < line.length && picked.length < limit; i += 1) {
    const item = line[i]
    if (!unfinished(item.point)) continue
    const first = picked.length === 0
    const sameUnit = item.stage.id === currentStageId
    const reason = first
      ? `当前单元 ${item.stage.title}`
      : sameUnit
        ? `同一单元往前 · ${item.stage.title}`
        : `下一单元 · ${item.stage.title}`
    picked.push({
      point_id: item.point.id,
      title: item.point.title,
      subject_id: subjectId || map.subject?.id,
      state: displayPointState(item.point.stats?.state),
      reason,
      stage_title: item.stage.title,
      opens_today: first,
    })
  }
  return picked
}

export interface SubjectPack {
  map: SubjectMap
  subjectId?: string
}

/** 多科时按当前单元轮流取，避免一门课占满名额。 */
export function recommendAdjacent(packs: SubjectPack[], limit = 5): NextItem[] {
  const lists = (packs || [])
    .filter(pack => pack?.map)
    .map(pack => recommendUnitForward(pack.map, pack.subjectId || pack.map.subject?.id, limit))
  const out: NextItem[] = []
  for (let index = 0; out.length < limit; index += 1) {
    let added = false
    for (const list of lists) {
      const item = list[index]
      if (!item) continue
      out.push(item)
      added = true
      if (out.length >= limit) break
    }
    if (!added) break
  }
  return out
}

export function unitNeighbors(stage: MapStage, pointId: string): { prev: MapPoint | null; next: MapPoint | null } {
  const points = orderedPoints(stage)
  const at = points.findIndex(point => point.id === pointId)
  if (at < 0) return { prev: null, next: null }
  return {
    prev: at > 0 ? points[at - 1] : null,
    next: at < points.length - 1 ? points[at + 1] : null,
  }
}
