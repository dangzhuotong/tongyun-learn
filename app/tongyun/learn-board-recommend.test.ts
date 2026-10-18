import { describe, it, expect } from 'vitest'
import type { SubjectMap } from './learn-board-api'
import { POINT_STATES, stateLabel } from './learn-board-api'
import {
  diffuseRecommendations,
  applyRecommendationsToMap,
} from './learn-board-recommend'

describe('learn-board recommendation (words 看板去掉「未解锁」，从当前在学的点往相邻点推荐)', () => {
  const sampleMap: SubjectMap = {
    subject: { id: 'java-fde', title: 'Java' },
    stages: [
      {
        id: 's1',
        title: '基础语法',
        ord: 1,
        passed: true,
        points: [
          { id: 'p1', title: '变量与类型', ord: 1, prereqs: [], stats: { state: 'mastered' } },
          { id: 'p2', title: '流程控制', ord: 2, prereqs: [{ id: 'p1', kind: 'hard' }], stats: { state: 'mastered' } },
        ],
      },
      {
        id: 's2',
        title: '面向对象',
        ord: 2,
        passed: false,
        points: [
          // p3 正在学习
          { id: 'p3', title: '类与对象', ord: 1, prereqs: [{ id: 'p2', kind: 'hard' }], stats: { state: 'learning' } },
          // p4 依赖 p3（下游相邻点），原为 locked
          { id: 'p4', title: '封装与继承', ord: 2, prereqs: [{ id: 'p3', kind: 'hard' }], stats: { state: 'locked' } },
          // p5 依赖 p4（2 步扩散）
          { id: 'p5', title: '多态与接口', ord: 3, prereqs: [{ id: 'p4', kind: 'hard' }], stats: { state: 'locked' } },
        ],
      },
      {
        id: 's3',
        title: '高级进阶',
        ord: 3,
        passed: false,
        points: [
          // p6 较远未解锁点
          { id: 'p6', title: '泛型与反射', ord: 1, prereqs: [{ id: 'p5', kind: 'hard' }], stats: { state: 'locked' } },
        ],
      },
    ],
  }

  it('recommends adjacent points starting from current learning points', () => {
    const recs = diffuseRecommendations(sampleMap, { maxHops: 2, limit: 5 })
    expect(recs.length).toBeGreaterThan(0)

    // 首个推荐点应是由 p3 直接依赖的相邻后置点 p4
    const firstRec = recs[0]
    expect(firstRec.pointId).toBe('p4')
    expect(firstRec.title).toBe('封装与继承')
    expect(firstRec.sourcePointId).toBe('p3')
    expect(firstRec.sourcePointTitle).toBe('类与对象')
    expect(firstRec.distance).toBe(1)
    expect(firstRec.reason).toContain('类与对象')

    // 2 步扩散应推荐 p5
    const secondRec = recs.find(r => r.pointId === 'p5')
    expect(secondRec).toBeDefined()
    expect(secondRec?.distance).toBe(2)
  })

  it('does not recommend already mastered or learned points', () => {
    const recs = diffuseRecommendations(sampleMap)
    const recIds = recs.map(r => r.pointId)
    expect(recIds).not.toContain('p1')
    expect(recIds).not.toContain('p2')
    expect(recIds).not.toContain('p3') // 正在学习的点本身不重复推荐
  })

  it('falls back to available or earliest unpassed stage point if no point is in learning', () => {
    const initialMap: SubjectMap = {
      subject: { id: 'java-fde', title: 'Java' },
      stages: [
        {
          id: 's1',
          title: '入门',
          ord: 1,
          passed: false,
          points: [
            { id: 'p1', title: '开始学习', ord: 1, prereqs: [], stats: { state: 'available' } },
            { id: 'p2', title: '第二步', ord: 2, prereqs: [{ id: 'p1', kind: 'hard' }], stats: { state: 'locked' } },
          ],
        },
      ],
    }

    const recs = diffuseRecommendations(initialMap)
    expect(recs.length).toBeGreaterThan(0)
    expect(recs[0].pointId).toBe('p2')
  })

  it('removes locked state from map and applies recommended state to adjacent points', () => {
    const applied = applyRecommendationsToMap(sampleMap)
    const s2Points = applied.stages[1].points

    // p3 依然是 learning
    const p3 = s2Points.find(p => p.id === 'p3')
    expect(p3?.stats.state).toBe('learning')

    // p4 变为 recommended
    const p4 = s2Points.find(p => p.id === 'p4')
    expect(p4?.stats.state).toBe('recommended')
    expect(p4?.stats.recommendReason).toBeDefined()

    // 较远且未被推荐的 locked 点（如 p6）被过滤移除，不再在看板显示「未解锁」
    const allRemainingPoints = applied.stages.flatMap(s => s.points)
    const states = allRemainingPoints.map(p => p.stats.state)
    expect(states).not.toContain('locked')
    for (const st of states) {
      expect(stateLabel(st)).not.toBe('未解锁')
    }
  })

  it('guarantees that POINT_STATES and stateLabel never display 未解锁', () => {
    expect(POINT_STATES.map(s => s.label)).not.toContain('未解锁')
    expect(POINT_STATES.map(s => s.key)).not.toContain('locked')
    expect(POINT_STATES.map(s => s.key)).toContain('recommended')
    expect(stateLabel('recommended')).toBe('推荐')
    expect(stateLabel('locked')).not.toBe('未解锁')
  })
})
