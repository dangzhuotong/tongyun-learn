import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  calculateSubjectNewCap,
  formatEndScreenSummary,
  getDefaultNewCardCap,
  getSubjectScore,
  getSubjectWeakness,
  isProjectCard,
  scheduleCurriculum,
  STAGE_WEIGHTS,
} from './scheduler'
import type { CurriculumCard, SubjectConfig } from './types'

const NOW = 1_800_000_000_000
const DAY = 24 * 3600 * 1000

describe('Curriculum Scheduler - Rule 1: Due reviews first, sorted by days overdue, daily cap 60', () => {
  it('places due review cards before new cards in the scheduled queue', () => {
    const subjects: SubjectConfig[] = [
      { id: 'en', stage: 'main', accuracy7d: 0.8 },
    ]
    const reviews: CurriculumCard[] = [
      { id: 'rev-1', subject: 'en', due: NOW - 2 * DAY, isReview: true },
    ]
    const newCards: CurriculumCard[] = [
      { id: 'new-1', subject: 'en', isReview: false },
    ]

    const result = scheduleCurriculum({
      subjects,
      reviews,
      newCards,
      now: NOW,
    })

    expect(result.items.map(i => i.id)).toEqual(['rev-1', 'new-1'])
    expect(result.reviewItems.map(i => i.id)).toEqual(['rev-1'])
    expect(result.newItems.map(i => i.id)).toEqual(['new-1'])
  })

  it('sorts due reviews descending by days overdue (most overdue first)', () => {
    const subjects: SubjectConfig[] = [
      { id: 'java', stage: 'main' },
    ]
    const reviews: CurriculumCard[] = [
      { id: 'rev-1day', subject: 'java', daysOverdue: 1 },
      { id: 'rev-10days', subject: 'java', daysOverdue: 10 },
      { id: 'rev-3days', subject: 'java', daysOverdue: 3 },
      { id: 'rev-0day', subject: 'java', daysOverdue: 0 },
    ]

    const result = scheduleCurriculum({
      subjects,
      reviews,
      now: NOW,
    })

    expect(result.reviewItems.map(i => i.id)).toEqual([
      'rev-10days',
      'rev-3days',
      'rev-1day',
      'rev-0day',
    ])
  })

  it('caps daily reviews at 60 cards when overdue reviews exceed 60', () => {
    const subjects: SubjectConfig[] = [
      { id: 'java', stage: 'main' },
    ]
    const reviews: CurriculumCard[] = Array.from({ length: 75 }, (_, i) => ({
      id: `rev-${i}`,
      subject: 'java',
      daysOverdue: i, // 0 to 74
    }))

    const result = scheduleCurriculum({
      subjects,
      reviews,
      dailyReviewCap: 60,
      now: NOW,
    })

    expect(result.dueTotal).toBe(75)
    expect(result.reviewItems).toHaveLength(60)
    // Most overdue (74 down to 15) should be scheduled
    expect(result.reviewItems[0].id).toBe('rev-74')
    expect(result.reviewItems[59].id).toBe('rev-15')
  })

  it('ensures review cards do not take slots for new-card subjects', () => {
    const subjects: SubjectConfig[] = [
      { id: 'ai', stage: 'main', accuracy7d: 0.9 },
      { id: 'java', stage: 'main', accuracy7d: 0.8 },
      { id: 'en', stage: 'main', accuracy7d: 0.7 },
    ]
    // Review is from 'en'
    const reviews: CurriculumCard[] = [
      { id: 'rev-en-1', subject: 'en', daysOverdue: 2 },
    ]
    // New cards available for all subjects
    const newCards: Record<string, CurriculumCard[]> = {
      ai: [{ id: 'new-ai-1', subject: 'ai' }],
      java: [{ id: 'new-java-1', subject: 'java' }],
      en: [{ id: 'new-en-1', subject: 'en' }],
    }

    const result = scheduleCurriculum({
      subjects,
      reviews,
      newCards,
      minNewSubjects: 2,
      maxNewSubjects: 3,
      now: NOW,
    })

    // Selected subjects for new cards are chosen independently of review subjects
    expect(result.selectedSubjects).toEqual(['en', 'java', 'ai'])
    expect(result.reviewItems).toHaveLength(1)
    expect(result.reviewItems[0].subject).toBe('en')
  })
})

describe('Curriculum Scheduler - Rule 2: Pick 2-3 subjects for new cards by stage weight x weakness', () => {
  it('applies stage weights main=3, maintain=2, light=1', () => {
    expect(STAGE_WEIGHTS.main).toBe(3)
    expect(STAGE_WEIGHTS.maintain).toBe(2)
    expect(STAGE_WEIGHTS.light).toBe(1)
  })

  it('ranks subjects by stage weight x weakness score', () => {
    const s1: SubjectConfig = { id: 's1', stage: 'main', weakness: 0.5 } // 3 * 0.5 = 1.5
    const s2: SubjectConfig = { id: 's2', stage: 'maintain', weakness: 0.9 } // 2 * 0.9 = 1.8
    const s3: SubjectConfig = { id: 's3', stage: 'light', weakness: 0.8 } // 1 * 0.8 = 0.8

    expect(getSubjectScore(s1)).toBe(1.5)
    expect(getSubjectScore(s2)).toBe(1.8)
    expect(getSubjectScore(s3)).toBe(0.8)

    const result = scheduleCurriculum({
      subjects: [s1, s2, s3],
      now: NOW,
    })

    // s2 (1.8) > s1 (1.5) > s3 (0.8)
    expect(result.selectedSubjects[0]).toBe('s2')
    expect(result.selectedSubjects[1]).toBe('s1')
  })

  it('picks 2-3 subjects for new cards when multiple subjects are available', () => {
    const subjects: SubjectConfig[] = [
      { id: 'sub-1', stage: 'main', weakness: 0.9 }, // 2.7
      { id: 'sub-2', stage: 'main', weakness: 0.8 }, // 2.4
      { id: 'sub-3', stage: 'maintain', weakness: 0.9 }, // 1.8
      { id: 'sub-4', stage: 'maintain', weakness: 0.5 }, // 1.0
      { id: 'sub-5', stage: 'light', weakness: 0.3 }, // 0.3
    ]

    const result = scheduleCurriculum({
      subjects,
      minNewSubjects: 2,
      maxNewSubjects: 3,
      now: NOW,
    })

    expect(result.selectedSubjects).toHaveLength(3)
    expect(result.selectedSubjects).toEqual(['sub-1', 'sub-2', 'sub-3'])
  })
})

describe('Curriculum Scheduler - Rule 3: Daily new-card caps and boundary conditions', () => {
  it('configures default daily caps (en: 8, java/ai main: 6, maintain: 2, others: 3)', () => {
    expect(getDefaultNewCardCap({ id: 'en', stage: 'main' })).toBe(8)
    expect(getDefaultNewCardCap({ id: 'english', stage: 'main' })).toBe(8)
    expect(getDefaultNewCardCap({ id: 'java', stage: 'main' })).toBe(6)
    expect(getDefaultNewCardCap({ id: 'ai', stage: 'main' })).toBe(6)
    expect(getDefaultNewCardCap({ id: 'any-subj', stage: 'maintain' })).toBe(2)
    expect(getDefaultNewCardCap({ id: 'other-subj', stage: 'light' })).toBe(3)
  })

  it('allows custom configurable per-subject daily new-card cap', () => {
    const custom: SubjectConfig = { id: 'en', stage: 'main', dailyNewCap: 15 }
    expect(getDefaultNewCardCap(custom)).toBe(15)
    expect(calculateSubjectNewCap(custom)).toBe(15)
  })

  describe('7-day accuracy <70% boundary test (70% and <70%)', () => {
    it('does NOT halve new cards at boundary 70% (0.70)', () => {
      const subj70: SubjectConfig = { id: 'en', stage: 'main', accuracy7d: 0.70 }
      expect(calculateSubjectNewCap(subj70)).toBe(8)

      const java70: SubjectConfig = { id: 'java', stage: 'main', accuracy7d: 70 } // percentage form
      expect(calculateSubjectNewCap(java70)).toBe(6)
    })

    it('halves new cards when accuracy is strictly below 70% (e.g. 69.9% or 0.69)', () => {
      const en69: SubjectConfig = { id: 'en', stage: 'main', accuracy7d: 0.69 }
      expect(calculateSubjectNewCap(en69)).toBe(4) // 8 / 2 = 4

      const java69: SubjectConfig = { id: 'java', stage: 'main', accuracy7d: 69 }
      expect(calculateSubjectNewCap(java69)).toBe(3) // 6 / 2 = 3

      const maintain69: SubjectConfig = { id: 'm', stage: 'maintain', accuracy7d: 0.65 }
      expect(calculateSubjectNewCap(maintain69)).toBe(1) // 2 / 2 = 1

      const other69: SubjectConfig = { id: 'other', stage: 'light', accuracy7d: 0.50 }
      expect(calculateSubjectNewCap(other69)).toBe(1) // floor(3 / 2) = 1
    })
  })

  describe('Overdue backlog >50 boundary test (50 and 51)', () => {
    it('allows new cards when overdue backlog is exactly 50 (boundary 50)', () => {
      const subjects: SubjectConfig[] = [
        { id: 'en', stage: 'main', accuracy7d: 0.8 },
      ]
      const newCards: CurriculumCard[] = [
        { id: 'nc-1', subject: 'en' },
        { id: 'nc-2', subject: 'en' },
      ]

      const result = scheduleCurriculum({
        subjects,
        newCards,
        overdueBacklog: 50, // Boundary: exactly 50
        now: NOW,
      })

      expect(result.newCardsBlockedByBacklog).toBe(false)
      expect(result.newItems).toHaveLength(2)
      expect(result.selectedSubjects).toEqual(['en'])
    })

    it('blocks all new cards when overdue backlog is 51 (> 50 boundary)', () => {
      const subjects: SubjectConfig[] = [
        { id: 'en', stage: 'main', accuracy7d: 0.8 },
      ]
      const newCards: CurriculumCard[] = [
        { id: 'nc-1', subject: 'en' },
        { id: 'nc-2', subject: 'en' },
      ]

      const result = scheduleCurriculum({
        subjects,
        newCards,
        overdueBacklog: 51, // Boundary: 51 > 50
        now: NOW,
      })

      expect(result.newCardsBlockedByBacklog).toBe(true)
      expect(result.newItems).toHaveLength(0)
      expect(result.selectedSubjects).toHaveLength(0)
    })
  })

  describe('Light subjects <= 1-2x/week rule', () => {
    it('permits scheduling new cards if light subject trained 1x this week', () => {
      const subjects: SubjectConfig[] = [
        { id: 'art', stage: 'light', trainedThisWeek: 1, maxLightTimesPerWeek: 2, weakness: 1 },
      ]
      const newCards: CurriculumCard[] = [{ id: 'art-1', subject: 'art' }]

      const result = scheduleCurriculum({
        subjects,
        newCards,
        now: NOW,
      })

      expect(result.selectedSubjects).toContain('art')
      expect(result.newItems).toHaveLength(1)
    })

    it('excludes light subject from new cards once it reached 2x this week', () => {
      const subjects: SubjectConfig[] = [
        { id: 'art', stage: 'light', trainedThisWeek: 2, maxLightTimesPerWeek: 2, weakness: 1 },
        { id: 'en', stage: 'main', weakness: 0.5 },
      ]
      const newCards: CurriculumCard[] = [
        { id: 'art-1', subject: 'art' },
        { id: 'en-1', subject: 'en' },
      ]

      const result = scheduleCurriculum({
        subjects,
        newCards,
        now: NOW,
      })

      expect(result.selectedSubjects).not.toContain('art')
      expect(result.selectedSubjects).toContain('en')
    })
  })

  describe('Project cards never in daily queue rule', () => {
    it('excludes project cards from both reviews and new cards', () => {
      const subjects: SubjectConfig[] = [{ id: 'java', stage: 'main' }]
      const reviews: CurriculumCard[] = [
        { id: 'proj-rev-1', subject: 'java', daysOverdue: 5, isProject: true },
        { id: 'proj-rev-2', subject: 'java', daysOverdue: 4, type: 'project' },
        { id: 'proj-rev-3', subject: 'java', daysOverdue: 3, tags: ['project'] },
        { id: 'valid-rev', subject: 'java', daysOverdue: 2 },
      ]
      const newCards: CurriculumCard[] = [
        { id: 'proj-new-1', subject: 'java', isProject: true },
        { id: 'proj-new-2', subject: 'java', type: 'project' },
        { id: 'valid-new', subject: 'java' },
      ]

      const result = scheduleCurriculum({
        subjects,
        reviews,
        newCards,
        now: NOW,
      })

      expect(result.items.map(i => i.id)).toEqual(['valid-rev', 'valid-new'])
      expect(result.items.some(isProjectCard)).toBe(false)
    })
  })
})

describe('End screen format and homepage button requirement', () => {
  it('formats end screen as 今天到期N、已复习M、本周X天 without countdown or streak', () => {
    const summary = formatEndScreenSummary(12, 10, 4)
    expect(summary).toBe('今天到期12、已复习10、本周4天')

    // Confirm no countdown and no streak keywords
    expect(summary).not.toContain('倒计时')
    expect(summary).not.toContain('countdown')
    expect(summary).not.toContain('连续')
    expect(summary).not.toContain('streak')
  })

  it('ensures practice.vue renders end screen with 今天到期N、已复习M、本周X天 and without countdown/streak', () => {
    const practiceVue = readFileSync(resolve(__dirname, '../../pages/practice.vue'), 'utf-8')
    expect(practiceVue).toContain('data-testid="end-summary"')
    expect(practiceVue).toContain('formatEndScreenSummary')
    expect(practiceVue).not.toContain('倒计时')
    expect(practiceVue).not.toContain('countdown')
    expect(practiceVue).not.toContain('连续打卡')
    expect(practiceVue).not.toContain('streak')
  })

  it('ensures homepage (index.vue) has exactly one 开始学 button', () => {
    const indexVue = readFileSync(resolve(__dirname, '../../pages/index.vue'), 'utf-8')

    // Check data-testid="start-learn"
    const startLearnMatches = indexVue.match(/data-testid="start-learn"/g)
    expect(startLearnMatches).not.toBeNull()
    expect(startLearnMatches?.length).toBe(1)

    // Check Chinese button text "开始学"
    const buttonTextMatches = indexVue.match(/开始学/g)
    expect(buttonTextMatches).not.toBeNull()
    expect(buttonTextMatches?.length).toBe(1)
  })
})
