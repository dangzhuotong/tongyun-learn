import { describe, expect, it } from 'vitest'
import { WordPracticeMode, WordPracticeType } from '@/core/types/enum.ts'
import {
  BUILTIN_FLOWS,
  CURRENT_FLOW_VERSION,
  GROUP_SIZE,
  STEP_TEMPLATE_META,
  getAllBuiltinFlowIds,
  getFlowConfig,
  getFlowIdForMode,
  materializeWordAdvance,
} from './practice-flow-config'

describe('step templates and group size', () => {
  it('maps every practice step to its practice type', () => {
    expect(GROUP_SIZE).toBe(7)
    expect(STEP_TEMPLATE_META.followWrite.practiceType).toBe(WordPracticeType.FollowWrite)
    expect(STEP_TEMPLATE_META.spell.practiceType).toBe(WordPracticeType.Spell)
    expect(STEP_TEMPLATE_META.identify.practiceType).toBe(WordPracticeType.Identify)
    expect(STEP_TEMPLATE_META.listen.practiceType).toBe(WordPracticeType.Listen)
    expect(STEP_TEMPLATE_META.dictation.practiceType).toBe(WordPracticeType.Dictation)
  })
})

describe('materializeWordAdvance', () => {
  it('defaults to a plain increment rule', () => {
    expect(materializeWordAdvance()).toEqual({ type: 'increment' })
    expect(materializeWordAdvance({ type: 'increment' })).toEqual({ type: 'increment' })
  })

  it('keeps wordLoop group size and defaults sub-steps to empty', () => {
    expect(materializeWordAdvance({ type: 'wordLoop', groupSize: 7, subSteps: [{ templateId: 'spell' }] })).toEqual({
      type: 'wordLoop',
      groupSize: 7,
      subSteps: [{ templateId: 'spell' }],
    })
    expect(materializeWordAdvance({ type: 'wordLoop', groupSize: 3 })).toEqual({
      type: 'wordLoop',
      groupSize: 3,
      subSteps: [],
    })
  })
})

describe('builtin flow lookup', () => {
  it('lists all builtin flows with a matching id and version', () => {
    expect(getAllBuiltinFlowIds()).toEqual([
      'system',
      'free',
      'review',
      'identifyOnly',
      'dictationOnly',
      'listenOnly',
      'shuffle',
    ])
    for (const [id, flow] of Object.entries(BUILTIN_FLOWS)) {
      expect(flow.id).toBe(id)
      expect(flow.version).toBe(CURRENT_FLOW_VERSION)
      expect(flow.nodes.length).toBeGreaterThan(0)
    }
  })

  it('maps each concrete mode to its flow, and Custom to custom', () => {
    expect(getFlowIdForMode(WordPracticeMode.System)).toBe('system')
    expect(getFlowIdForMode(WordPracticeMode.Free)).toBe('free')
    expect(getFlowIdForMode(WordPracticeMode.Review)).toBe('review')
    expect(getFlowIdForMode(WordPracticeMode.IdentifyOnly)).toBe('identifyOnly')
    expect(getFlowIdForMode(WordPracticeMode.DictationOnly)).toBe('dictationOnly')
    expect(getFlowIdForMode(WordPracticeMode.ListenOnly)).toBe('listenOnly')
    expect(getFlowIdForMode(WordPracticeMode.Shuffle)).toBe('shuffle')
    expect(getFlowIdForMode(WordPracticeMode.Custom)).toBe('custom')
  })

  it('falls back to the system flow for unknown modes and ids', () => {
    expect(getFlowIdForMode(WordPracticeMode.ShuffleWordsTest)).toBe('system')
    expect(getFlowConfig('shuffle')).toBe(BUILTIN_FLOWS.shuffle)
    expect(getFlowConfig('does-not-exist')).toBe(BUILTIN_FLOWS.system)
  })
})
