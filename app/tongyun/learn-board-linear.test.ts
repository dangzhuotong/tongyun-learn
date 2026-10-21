import { describe, expect, it } from 'vitest'
import type { SubjectMap } from './learn-board-api'
import { displayPointState, foldPointCounts, recommendAdjacent, unitNeighbors } from './learn-board-linear'

function point(
  id: string,
  title: string,
  state: string,
  ord: number,
  prereqs: { id: string; kind: string }[] = []
) {
  return { id, title, ord, prereqs, stats: { state } }
}

const javaMap: SubjectMap = {
  subject: { id: 'java-fde', title: 'Java' },
  stages: [
    {
      id: 'u1',
      title: '语法',
      ord: 1,
      passed: true,
      points: [point('p1', '变量', 'mastered', 1), point('p2', '类型', 'learned', 2)],
    },
    {
      id: 'u2',
      title: '类与对象',
      ord: 2,
      passed: false,
      points: [
        point('p3', '类', 'learning', 1),
        point('p4', '对象', 'locked', 2, [{ id: 'p9', kind: 'hard' }]),
        point('p5', '继承', 'mastered', 3),
        point('p6', '接口', 'available', 4),
      ],
    },
    {
      id: 'u3',
      title: '集合',
      ord: 3,
      passed: false,
      points: [point('p7', 'List', 'locked', 1), point('p8', 'Map', 'available', 2)],
    },
  ],
}

describe('linear unit recommendations', () => {
  it('treats locked as available and drops it from counts', () => {
    expect(displayPointState('locked')).toBe('available')
    expect(displayPointState(null)).toBe('available')
    expect(displayPointState('mastered')).toBe('mastered')
    expect(foldPointCounts({ locked: 2, available: 1, mastered: 3 })).toEqual({
      available: 3,
      mastered: 3,
    })
  })

  it('recommends forward from the current unit and ignores prerequisite edges', () => {
    const java = recommendAdjacent([{ map: javaMap, subjectId: 'java-fde' }], 5)
    expect(java.map(item => item.point_id)).toEqual(['p3', 'p4', 'p6', 'p7', 'p8'])
    expect(java[0].reason).toBe('当前单元 类与对象')
    expect(java[0].opens_today).toBe(true)
    expect(java[1].reason).toBe('同一单元往前 · 类与对象')
    expect(java[1].state).toBe('available')
    expect(java[3].reason).toBe('下一单元 · 集合')
    expect(java.every(item => item.state !== 'locked')).toBe(true)
    expect(java.map(item => item.subject_id)).toEqual(['java-fde', 'java-fde', 'java-fde', 'java-fde', 'java-fde'])
  })

  it('does not walk backward into a finished unit', () => {
    const next = recommendAdjacent([{ map: javaMap }], 2)
    expect(next.map(item => item.point_id)).toEqual(['p3', 'p4'])
    expect(next.some(item => item.point_id === 'p1' || item.point_id === 'p2')).toBe(false)
  })

  it('alternates subjects so one unit does not take the whole list', () => {
    const english: SubjectMap = {
      subject: { id: 'english', title: '英语' },
      stages: [
        {
          id: 'e1',
          title: '核心术语',
          ord: 1,
          passed: false,
          points: [point('e1', 'prompt', 'available', 1), point('e2', 'token', 'learning', 2)],
        },
      ],
    }
    const next = recommendAdjacent(
      [
        { map: javaMap, subjectId: 'java-fde' },
        { map: english, subjectId: 'english' },
      ],
      4
    )
    expect(next.map(item => item.point_id)).toEqual(['p3', 'e1', 'p4', 'e2'])
  })

  it('shows the previous and next point inside the unit', () => {
    const stage = javaMap.stages[1]
    expect(unitNeighbors(stage, 'p4').prev?.id).toBe('p3')
    expect(unitNeighbors(stage, 'p4').next?.id).toBe('p5')
    expect(unitNeighbors(stage, 'p3').prev).toBeNull()
    expect(unitNeighbors(stage, 'missing').next).toBeNull()
  })
})
