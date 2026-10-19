import { describe, expect, it } from 'vitest'
import type { PracticeFlowConfig, PracticeFlowCursor, PracticeFlowStep } from './practice-flow-types'
import { getPracticeFlowDisplayState } from './practice-flow-display'

function cursor(over: Partial<PracticeFlowCursor> = {}): PracticeFlowCursor {
  return { nodeIndex: 0, stepIndex: 0, inWrongWordClear: false, loop: null, endActionIndex: null, ...over }
}

const step = (templateId: PracticeFlowStep['templateId']): PracticeFlowStep => ({ templateId })

const multiNodeConfig: PracticeFlowConfig = {
  id: 'multi',
  version: 1,
  mode: 0,
  label: 'flow',
  nodes: [
    { id: 'new', label: 'new_words', source: 'taskNew', steps: [step('followWrite')] },
    { id: 'review', label: 'review', source: 'taskReview', steps: [step('identify')] },
  ],
}

const multiStepConfig: PracticeFlowConfig = {
  id: 'review',
  version: 1,
  mode: 6,
  label: 'review',
  nodes: [{ id: 'review', label: 'review', source: 'taskReview', steps: [step('identify'), step('listen'), step('dictation')] }],
}

describe('getPracticeFlowDisplayState', () => {
  it('returns an empty stage model when the flow has no nodes', () => {
    const config: PracticeFlowConfig = { id: 'empty', version: 1, mode: 0, label: 'flow', nodes: [] }
    const state = getPracticeFlowDisplayState({ config, cursor: cursor(), wordIndex: 0, wordCount: 0 })
    expect(state).toEqual({ status: 'flow', stages: [], showSkipStep: false })
  })

  it('collapses a single-node single-step flow into one full stage', () => {
    const config: PracticeFlowConfig = {
      id: 'free',
      version: 1,
      mode: 1,
      label: 'free',
      nodes: [{ id: 'practice', label: 'free_practice', source: 'current', steps: [step('followWrite')] }],
    }
    const state = getPracticeFlowDisplayState({ config, cursor: cursor(), wordIndex: 3, wordCount: 10 })
    expect(state.status).toBe('free')
    expect(state.showSkipStep).toBe(false)
    expect(state.stages).toEqual([{ name: '', ratio: 100, percentage: 30, active: true }])
  })

  it('builds step children for a single node with several steps', () => {
    const state = getPracticeFlowDisplayState({
      config: multiStepConfig,
      cursor: cursor({ stepIndex: 1 }),
      wordIndex: 5,
      wordCount: 10,
    })
    expect(state.status).toBe('review · listen')
    expect(state.showSkipStep).toBe(true)
    expect(state.stages).toHaveLength(1)
    const node = state.stages[0]
    expect(node).toMatchObject({ name: 'review', ratio: 100, percentage: 50, active: true })
    expect(node.children?.map(child => child.name)).toEqual(['identify', 'listen', 'dictation'])
    expect(node.children?.map(child => child.percentage)).toEqual([100, 50, 0])
    expect(node.children?.map(child => child.active)).toEqual([false, true, false])
  })

  it('splits several nodes into completed/current stages with fixed ratios', () => {
    const state = getPracticeFlowDisplayState({
      config: multiNodeConfig,
      cursor: cursor({ nodeIndex: 1 }),
      wordIndex: 0,
      wordCount: 5,
    })
    expect(state.status).toBe('review · identify')
    expect(state.showSkipStep).toBe(true)
    expect(state.stages.map(stage => `${stage.name}:${stage.ratio}:${stage.percentage}:${stage.active}`)).toEqual([
      'new_words:30:100:false',
      'review:70:0:true',
    ])
    expect(state.stages[0].children).toBeUndefined()
  })

  it('uses the translate function for the status line', () => {
    const translate = (key: string) => `t:${key}`
    const state = getPracticeFlowDisplayState({
      config: multiNodeConfig,
      cursor: cursor(),
      wordIndex: 0,
      wordCount: 1,
      translate,
    })
    expect(state.status).toBe('t:new_words · t:followWrite')
  })

  it('lets loop state win over the node label', () => {
    const state = getPracticeFlowDisplayState({
      config: multiNodeConfig,
      cursor: cursor({ loop: { startIndex: 0, endIndex: 6, subStepIndex: 0 } }),
      wordIndex: 0,
      wordCount: 5,
    })
    expect(state.status).toBe('小组巩固')
  })

  it('labels the wrong-word-clear status through translate', () => {
    const state = getPracticeFlowDisplayState({
      config: multiNodeConfig,
      cursor: cursor({ inWrongWordClear: true }),
      wordIndex: 0,
      wordCount: 5,
      translate: key => `t:${key}`,
    })
    expect(state.status).toBe('t:review_wrong_words')
  })

  it('reports zero progress when wordCount is zero', () => {
    const state = getPracticeFlowDisplayState({
      config: multiNodeConfig,
      cursor: cursor({ nodeIndex: 1 }),
      wordIndex: 0,
      wordCount: 0,
    })
    expect(state.stages[1].percentage).toBe(0)
  })
})
