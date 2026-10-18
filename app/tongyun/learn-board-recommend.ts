// tongyun: 学习看板从当前在学的点往相邻点扩散推荐
import type { MapPoint, MapStage, SubjectMap } from './learn-board-api'

export interface RecommendedAdjacentPoint {
  pointId: string
  title: string
  stageId?: string
  stageTitle?: string
  sourcePointId: string
  sourcePointTitle: string
  reason: string
  distance: number
}

export interface RecommendationOptions {
  /** 扩散最大步数（默认 2 步） */
  maxHops?: number
  /** 最多推荐点数（默认 10 个） */
  limit?: number
  /** 是否隐藏未解锁且非推荐的点（默认 true，彻底不在看板展示「未解锁」） */
  hideLocked?: boolean
}

/**
 * 从当前在学的点（state === 'learning'）向相邻点（前置/后置/同阶段相邻）扩散推荐
 */
export function diffuseRecommendations(
  map: SubjectMap | null | undefined,
  options?: RecommendationOptions
): RecommendedAdjacentPoint[] {
  if (!map?.stages || map.stages.length === 0) {
    return []
  }

  const maxHops = options?.maxHops ?? 2
  const limit = options?.limit ?? 10

  const pointMap = new Map<string, MapPoint>()
  const pointStage = new Map<string, MapStage>()
  // 后置依赖：prereqId -> 依赖它的点列表（学习该点后可推进的下一步）
  const downstream = new Map<string, string[]>()
  // 前置依赖：pointId -> 它的前置点列表
  const upstream = new Map<string, string[]>()
  // 同阶段同序相邻点：pointId -> 相邻点列表
  const stageNeighbors = new Map<string, string[]>()

  for (const st of map.stages) {
    const pts = (st.points || []).slice().sort((a, b) => (a.ord ?? 0) - (b.ord ?? 0))
    for (let i = 0; i < pts.length; i++) {
      const p = pts[i]
      pointMap.set(p.id, p)
      pointStage.set(p.id, st)

      if (i > 0) {
        const prev = pts[i - 1]
        if (!stageNeighbors.has(p.id)) stageNeighbors.set(p.id, [])
        stageNeighbors.get(p.id)!.push(prev.id)
      }
      if (i < pts.length - 1) {
        const next = pts[i + 1]
        if (!stageNeighbors.has(p.id)) stageNeighbors.set(p.id, [])
        stageNeighbors.get(p.id)!.push(next.id)
      }

      for (const pr of p.prereqs || []) {
        if (!downstream.has(pr.id)) downstream.set(pr.id, [])
        downstream.get(pr.id)!.push(p.id)

        if (!upstream.has(p.id)) upstream.set(p.id, [])
        upstream.get(p.id)!.push(pr.id)
      }
    }
  }

  // 1. 寻找当前在学的点作为种子
  const allPoints = Array.from(pointMap.values())
  let seedPoints = allPoints.filter(p => p.stats?.state === 'learning')

  // 若暂无「学习中」的点，回退到「可学」点，或首个未通过阶段的入口点
  if (seedPoints.length === 0) {
    seedPoints = allPoints.filter(p => p.stats?.state === 'available')
  }
  if (seedPoints.length === 0) {
    const firstUnpassed = map.stages.find(s => !s.passed) || map.stages[0]
    if (firstUnpassed && firstUnpassed.points?.length) {
      seedPoints = [firstUnpassed.points[0]]
    }
  }

  if (seedPoints.length === 0) {
    return []
  }

  // 2. BFS 向相邻点扩散推荐
  interface QueueItem {
    pointId: string
    distance: number
    sourceId: string
  }

  const queue: QueueItem[] = seedPoints.map(s => ({
    pointId: s.id,
    distance: 0,
    sourceId: s.id,
  }))

  const visited = new Set<string>(seedPoints.map(s => s.id))
  const recommendedIds = new Set<string>()
  const results: RecommendedAdjacentPoint[] = []

  while (queue.length > 0 && results.length < limit) {
    const current = queue.shift()!
    if (current.distance >= maxHops) {
      continue
    }

    // 邻居收集顺序：后置依赖（学完直接进阶）优先，其次同阶段后项，再前置
    const downs = downstream.get(current.pointId) || []
    const stageNexts = stageNeighbors.get(current.pointId) || []
    const ups = upstream.get(current.pointId) || []

    const candidates = [
      ...downs.map(id => ({ id, type: 'downstream' as const })),
      ...stageNexts.map(id => ({ id, type: 'stage' as const })),
      ...ups.map(id => ({ id, type: 'upstream' as const })),
    ]

    for (const cand of candidates) {
      if (visited.has(cand.id)) continue
      visited.add(cand.id)

      const target = pointMap.get(cand.id)
      if (!target) continue

      const state = target.stats?.state
      // 已掌握、已学过或正在学习的不重复作为推荐
      if (state === 'mastered' || state === 'learned' || state === 'learning') {
        continue
      }

      if (!recommendedIds.has(cand.id)) {
        recommendedIds.add(cand.id)
        const sourcePoint = pointMap.get(current.sourceId)
        const sourceTitle = sourcePoint?.title || current.sourceId

        let reason = ''
        if (current.distance === 0) {
          if (cand.type === 'downstream') {
            reason = `「${sourceTitle}」的后置进阶知识点`
          } else if (cand.type === 'stage') {
            reason = `与正在学习的「${sourceTitle}」同阶段相邻`
          } else {
            reason = `与正在学习的「${sourceTitle}」相邻`
          }
        } else {
          reason = `由正在学习的「${sourceTitle}」扩散推荐`
        }

        results.push({
          pointId: target.id,
          title: target.title,
          stageId: pointStage.get(target.id)?.id,
          stageTitle: pointStage.get(target.id)?.title,
          sourcePointId: current.sourceId,
          sourcePointTitle: sourceTitle,
          reason,
          distance: current.distance + 1,
        })

        if (results.length >= limit) break
      }

      queue.push({
        pointId: cand.id,
        distance: current.distance + 1,
        sourceId: current.sourceId,
      })
    }
  }

  return results
}

/**
 * 将扩散推荐应用到整张地图上：
 * 1. 相邻推荐点标记为 state = 'recommended'
 * 2. 彻底移除未解锁（locked）点，不再在看板显示「未解锁」
 */
export function applyRecommendationsToMap(
  map: SubjectMap | null | undefined,
  options?: RecommendationOptions
): SubjectMap {
  if (!map?.stages) {
    return map as SubjectMap
  }

  const hideLocked = options?.hideLocked ?? true
  const recommendations = diffuseRecommendations(map, options)
  const recMap = new Map(recommendations.map(r => [r.pointId, r]))

  const newStages: MapStage[] = map.stages.map(st => {
    const newPoints: MapPoint[] = []
    for (const p of st.points || []) {
      const rec = recMap.get(p.id)
      if (rec) {
        newPoints.push({
          ...p,
          stats: {
            ...p.stats,
            state: 'recommended',
            recommendReason: rec.reason,
            sourcePointTitle: rec.sourcePointTitle,
          },
        })
      } else if (p.stats?.state === 'locked') {
        // 看板不再显示「未解锁」：如果设置了 hideLocked 则不放入展示点列表
        if (!hideLocked) {
          newPoints.push({
            ...p,
            stats: {
              ...p.stats,
              state: 'available',
            },
          })
        }
      } else {
        newPoints.push({ ...p })
      }
    }

    return {
      ...st,
      points: newPoints,
    }
  })

  return {
    ...map,
    stages: newStages,
  }
}
