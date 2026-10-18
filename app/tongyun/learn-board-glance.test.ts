import { describe, it, expect } from 'vitest'
import type { SubjectMap } from './learn-board-api'
import {
  JAVA_SUBJECT_ID,
  boardSubjectLabel,
  mapProgressLine,
  mapStatusLine,
  resolveBoardSubjects,
  subjectSlot,
  summarizeMap,
  isPrereqsMet,
  getSuggestedNextPoints,
} from './learn-board-glance'

describe('learn-board subject slots', () => {
  it('recognizes java-fde and english even when english is listed first', () => {
    const subjects = [
      { id: 'english', title: '英语' },
      { id: JAVA_SUBJECT_ID, title: 'Java 基础' },
    ]
    expect(subjectSlot(subjects[0])).toBe('english')
    expect(subjectSlot(subjects[1])).toBe('java')
    expect(boardSubjectLabel(subjects[1])).toBe('Java')
    expect(boardSubjectLabel(subjects[0])).toBe('英语')

    const resolved = resolveBoardSubjects(subjects)
    expect(resolved.java?.id).toBe(JAVA_SUBJECT_ID)
    expect(resolved.english?.id).toBe('english')
    expect(resolved.ordered.map(s => s.id)).toEqual([JAVA_SUBJECT_ID, 'english'])
  })

  it('treats the only other subject as english when java is present', () => {
    const resolved = resolveBoardSubjects([
      { id: JAVA_SUBJECT_ID, title: 'Java' },
      { id: 'cet-vocab', title: '词汇' },
    ])
    expect(resolved.english?.id).toBe('cet-vocab')
    expect(resolved.ordered.map(s => s.id)).toEqual([JAVA_SUBJECT_ID, 'cet-vocab'])
  })

  it('does not guess english when several other subjects exist', () => {
    const resolved = resolveBoardSubjects([
      { id: 'math', title: '数学' },
      { id: 'physics', title: '物理' },
    ])
    expect(resolved.java).toBeNull()
    expect(resolved.english).toBeNull()
    expect(resolved.ordered.map(s => s.id)).toEqual(['math', 'physics'])
  })

  it('does not treat javascript as the java subject', () => {
    expect(subjectSlot({ id: 'javascript', title: 'JavaScript 入门' })).toBe('other')
  })
})

describe('map status summary', () => {
  const map: SubjectMap = {
    subject: { id: JAVA_SUBJECT_ID, title: 'Java' },
    stages: [
      {
        id: 's1',
        title: '语法',
        ord: 1,
        passed: true,
        points: [
          { id: 'p1', title: '变量', prereqs: [], stats: { state: 'mastered' } },
          { id: 'p2', title: '类型', prereqs: [], stats: { state: 'mastered' } },
        ],
      },
      {
        id: 's2',
        title: '类与对象',
        ord: 2,
        passed: false,
        points: [
          { id: 'p3', title: '类', prereqs: [], stats: { state: 'learning' } },
          { id: 'p4', title: '对象', prereqs: [], stats: { state: 'available' } },
        ],
      },
    ],
  }

  it('highlights the first unfinished stage and counts points', () => {
    const summary = summarizeMap(map)
    expect(summary.passedStages).toBe(1)
    expect(summary.totalStages).toBe(2)
    expect(summary.allPassed).toBe(false)
    expect(summary.currentOrd).toBe(2)
    expect(summary.currentTitle).toBe('类与对象')
    expect(summary.masteredPoints).toBe(2)
    expect(summary.totalPoints).toBe(4)
    expect(mapStatusLine(summary)).toBe('第 2 阶段 · 类与对象')
    expect(mapProgressLine(summary)).toBe('已通过 1 / 2 阶段 · 掌握 2 / 共 4')
  })

  it('says the map is finished when every stage passed', () => {
    const done = summarizeMap({
      ...map,
      stages: map.stages.map(s => ({ ...s, passed: true })),
    })
    expect(done.allPassed).toBe(true)
    expect(mapStatusLine(done)).toBe('地图已全部通过 · 2 / 2 阶段')
    expect(mapProgressLine(done)).toBe('全部阶段已通过 · 掌握 2 / 共 4')
  })

  it('handles a subject with no stages', () => {
    const empty = summarizeMap({ subject: { id: 'english', title: '英语' }, stages: [] })
    expect(mapStatusLine(empty)).toBe('这科还没有阶段')
    expect(mapProgressLine(empty)).toBe('还没有知识点')
  })

  it('maps unstarted points and legacy locked points to available without locked in summary', () => {
    const mapWithLocked: SubjectMap = {
      subject: { id: 'english', title: '英语' },
      stages: [
        {
          id: 's1',
          title: '基础',
          ord: 1,
          passed: false,
          points: [
            { id: 'p1', title: '词汇 1', prereqs: [], stats: { state: 'locked' } },
            { id: 'p2', title: '词汇 2', prereqs: [], stats: { state: null } },
            { id: 'p3', title: '词汇 3', prereqs: [], stats: { state: 'available' } },
          ],
        },
      ],
    }
    const summary = summarizeMap(mapWithLocked)
    expect(summary.totalPoints).toBe(3)
    expect(summary.counts.find(c => c.key === 'locked')).toBeUndefined()
    const availableCount = summary.counts.find(c => c.key === 'available')
    expect(availableCount?.count).toBe(3)
  })
})

describe('knowledge map suggested next calculation from prerequisites', () => {
  const map: SubjectMap = {
    subject: { id: 'tech-english', title: '技术英语' },
    stages: [
      {
        id: 's1',
        title: '阶段一',
        ord: 1,
        passed: false,
        points: [
          { id: 'p1', title: '基础词汇', prereqs: [], stats: { state: 'mastered' } },
          { id: 'p2', title: '进阶词汇', prereqs: [{ id: 'p1', kind: 'hard' }], stats: { state: 'available' } },
          { id: 'p3', title: '长难句', prereqs: [{ id: 'p2', kind: 'hard' }], stats: { state: 'available' } },
        ],
      },
      {
        id: 's2',
        title: '阶段二',
        ord: 2,
        passed: false,
        points: [
          { id: 'p4', title: '技术文档', prereqs: [{ id: 'p3', kind: 'soft' }], stats: { state: 'available' } },
          { id: 'p5', title: '独立模块', prereqs: [], stats: { state: 'available' } },
        ],
      },
    ],
  }

  it('evaluates whether prerequisites are met', () => {
    const lookup = new Map<string, any>()
    for (const st of map.stages) {
      for (const pt of st.points) {
        lookup.set(pt.id, pt)
      }
    }

    // p1 has no prereqs -> met
    expect(isPrereqsMet(lookup.get('p1'), lookup)).toBe(true)
    // p2 requires p1 which is mastered -> met
    expect(isPrereqsMet(lookup.get('p2'), lookup)).toBe(true)
    // p3 requires p2 which is only available -> not met
    expect(isPrereqsMet(lookup.get('p3'), lookup)).toBe(true === false)
    expect(isPrereqsMet(lookup.get('p3'), lookup)).toBe(false)
    // p5 has no prereqs -> met
    expect(isPrereqsMet(lookup.get('p5'), lookup)).toBe(true)
  })

  it('calculates suggested next points in order where prereqs are met and not yet mastered', () => {
    const nextPoints = getSuggestedNextPoints(map)
    const nextIds = nextPoints.map(p => p.id)

    // p1 is mastered so it is excluded
    expect(nextIds).not.toContain('p1')
    // p2 prereq (p1) is mastered, so p2 is suggested
    expect(nextIds).toContain('p2')
    // p3 prereq (p2) is not mastered/learned, so p3 is not suggested yet
    expect(nextIds).not.toContain('p3')
    // p5 has no prereqs, so p5 is suggested
    expect(nextIds).toContain('p5')
    // All points are openable (none locked), but suggested next follows prerequisite order
    expect(nextIds).toEqual(['p2', 'p5'])
  })

  it('suggests downstream points once upstream prerequisites are learned', () => {
    const updatedMap: SubjectMap = {
      ...map,
      stages: map.stages.map(st => ({
        ...st,
        points: st.points.map(pt => (pt.id === 'p2' ? { ...pt, stats: { state: 'learned' } } : pt)),
      })),
    }

    const nextPoints = getSuggestedNextPoints(updatedMap)
    const nextIds = nextPoints.map(p => p.id)

    // With p2 learned, p3 becomes suggested next
    expect(nextIds).toContain('p3')
    expect(nextIds).toContain('p5')
    expect(nextIds).not.toContain('p2')
  })
})
