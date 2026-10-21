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

  it('counts a locked point as available', () => {
    const summary = summarizeMap({
      subject: { id: JAVA_SUBJECT_ID, title: 'Java' },
      stages: [
        {
          id: 's1',
          title: '语法',
          ord: 1,
          passed: false,
          points: [{ id: 'p1', title: '变量', prereqs: [{ id: 'later', kind: 'hard' }], stats: { state: 'locked' } }],
        },
      ],
    })
    expect(summary.counts.map(item => item.key)).not.toContain('locked')
    expect(summary.counts.find(item => item.key === 'available')?.count).toBe(1)
    expect(summary.totalPoints).toBe(1)
  })

  it('handles a subject with no stages', () => {
    const empty = summarizeMap({ subject: { id: 'english', title: '英语' }, stages: [] })
    expect(mapStatusLine(empty)).toBe('这科还没有阶段')
    expect(mapProgressLine(empty)).toBe('还没有知识点')
  })
})
