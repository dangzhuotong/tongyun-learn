import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { loadBank, hasBank } from './bank'
import { activeCards, isSelfType, parseBank, validateBank } from './parse'
import { SUBJECTS, SUBJECT_IDS, getSubject, isSubjectType, requireSubject } from './registry'
import { gradeCard, gradeChoice, gradeText, isCodeQuestion } from './grade'
import {
  SELF_FAIL_DAYS,
  SELF_PARTIAL_DAYS,
  applySelfAssessment,
  selfIntervalDays,
  selfNextDue,
} from './self-assessment'
import type { Card, QuestionBank } from './types'
import subjectsJson from './subjects.json'

const root = process.cwd()
const read = (p: string) => readFileSync(resolve(root, p), 'utf8')

describe('题库解析：兼容现有 java / ai', () => {
  it('java-v0.1.json 原样加载，id 与答案不变', async () => {
    const bank = await loadBank('java')
    expect(bank.subject).toBe('java')
    expect(bank.points).toHaveLength(9)
    expect(bank.items).toHaveLength(20)
    const card = bank.items.find(c => c.id === 'java-0001')!
    expect(card.point_id).toBe('java.object.equals-hashcode')
    expect(card.answer).toBe('hashCode')
    expect(card.type).toBe('concept')
    // 旧题库没有 level/unit/map_point/refs/options/rubric/retired，也不该被凭空加上
    expect('retired' in card).toBe(false)
  })

  it('ai-v0.1.json 原样加载', async () => {
    const bank = await loadBank('ai')
    expect(bank.subject).toBe('ai')
    expect(bank.items.length).toBeGreaterThan(0)
    expect(bank.items.every(c => c.type === 'term' || c.type === 'concept' || c.type === 'code')).toBe(true)
  })

  it('新字段全可选：只有旧字段也能解析', () => {
    const bank = parseBank({
      subject: 'x',
      version: '0.1',
      points: [{ id: 'x.p1', title: '点1', prereq: [] }],
      items: [
        { id: 'x-1', point_id: 'x.p1', level: 1, type: 'term', prompt: '问', answer: '答' },
      ],
    })
    expect(bank.points[0]!.level).toBeUndefined()
    expect(bank.points[0]!.unit).toBeUndefined()
    expect(bank.items[0]!.accept).toBeUndefined()
  })

  it('points 支持可选 level / unit / map_point / refs，含显式 null', () => {
    const bank = parseBank({
      subject: 'y',
      version: '0.1',
      points: [{ id: 'y.p1', title: '点', prereq: [], level: 2, unit: 'C1', map_point: null, refs: ['jf.x'] }],
      items: [],
    })
    expect(bank.points[0]!.level).toBe(2)
    expect(bank.points[0]!.unit).toBe('C1')
    expect(bank.points[0]!.map_point).toBeNull()
    expect(bank.points[0]!.refs).toEqual(['jf.x'])
  })

  it('未知学科抛错，不回落 Java', async () => {
    await expect(loadBank('nope')).rejects.toThrow('未知学科')
    await expect(loadBank('java2')).rejects.toThrow()
  })
})

describe('注册表驱动类型与页面校验', () => {
  it('SUBJECTS 每项都有 load()，且与 subjects.json 对齐', () => {
    expect(SUBJECTS.length).toBeGreaterThan(0)
    expect(SUBJECTS.every(s => typeof s.load === 'function')).toBe(true)
    const jsonIds = (subjectsJson as { subjects: { id: string }[] }).subjects.map(s => s.id)
    expect(SUBJECT_IDS).toEqual(jsonIds.filter(id => hasBank(id)))
  })

  it('SubjectType 由注册表推导，isSubjectType 只认已注册学科', () => {
    expect(SUBJECT_IDS).toContain('java')
    expect(isSubjectType('java')).toBe(true)
    expect(isSubjectType('chem')).toBe(false)
  })

  it('getSubject / requireSubject 对未知学科抛错', () => {
    expect(getSubject('java').title).toBe('Java')
    expect(() => getSubject('nope')).toThrow('未知学科')
    expect(() => requireSubject('')).toThrow('缺少学科')
    expect(() => requireSubject(undefined)).toThrow('缺少学科')
  })

  it('注册表里每个学科都能 load 出对应 subject', async () => {
    for (const s of SUBJECTS) {
      const bank = await s.load()
      expect(bank.subject).toBe(s.id)
    }
  })
})

describe('判分：choice 自动判、code 按 type 判、oral/project 自评', () => {
  const choice: Card = {
    id: 'c-1', point_id: 'p', level: 1, type: 'choice', prompt: 'q', answer: 'B',
    options: ['A', 'B', 'C'], grading: 'auto',
  }
  const code: Card = {
    id: 'java-0003', point_id: 'p', level: 2, type: 'code', prompt: 'q',
    answer: 'return Objects.hash(name, age);',
    accept: ['Objects.hash(name, age)'], code: 'return Objects.hash(name, age);',
  }
  // 同一个 id 若被当成 term，走 accept 而不是 code 逻辑
  const termSameId: Card = { ...code, type: 'term' }
  const oral: Card = {
    id: 'o-1', point_id: 'p', level: 1, type: 'oral', prompt: 'q', answer: '自评完成',
    rubric: ['a', 'b', 'c'], grading: 'self',
  }

  it('choice 自动判分', () => {
    expect(gradeChoice(choice, 'B')).toBe(true)
    expect(gradeCard(choice, 'B')).toBe('correct')
    expect(gradeCard(choice, 'A')).toBe('wrong')
  })

  it('code 由 type === "code" 识别，不靠 id 白名单', () => {
    expect(isCodeQuestion(code)).toBe(true)
    expect(isCodeQuestion(termSameId)).toBe(false)
    expect(gradeText(code, 'return  Objects.hash(name,   age);')).toBe(true)
    expect(gradeCard(code, 'return Objects.hash(name, age)')).toBe('correct')
  })

  it('oral / project 返回 self', () => {
    expect(isSelfType('oral')).toBe(true)
    expect(isSelfType('project')).toBe(true)
    expect(gradeCard(oral, '')).toBe('self')
  })
})

describe('自评驱动间隔：不会 1 天 / 半会 3 天 / 会走正常间隔', () => {
  it('selfIntervalDays', () => {
    expect(selfIntervalDays('self_fail', 7)).toBe(SELF_FAIL_DAYS)
    expect(selfIntervalDays('self_partial', 7)).toBe(SELF_PARTIAL_DAYS)
    expect(selfIntervalDays('self_ok', 7)).toBe(7)
    expect(selfNextDue('self_fail', 7, 0)).toBe(SELF_FAIL_DAYS * 24 * 3600 * 1000)
  })

  it('applySelfAssessment：会前进一档、半会不动、不会重置', () => {
    const intervals = [1, 3, 7, 14, 30]
    const now = 0
    const ok = applySelfAssessment('self_ok', { box: 1, intervals, now })
    expect(ok.box).toBe(2)
    expect(ok.due).toBe(7 * 24 * 3600 * 1000)

    const partial = applySelfAssessment('self_partial', { box: 1, intervals, now })
    expect(partial.box).toBe(1)
    expect(partial.due).toBe(3 * 24 * 3600 * 1000)

    const fail = applySelfAssessment('self_fail', { box: 4, intervals, now })
    expect(fail.box).toBe(0)
    expect(fail.due).toBe(1 * 24 * 3600 * 1000)
  })
})

describe('choice / rubric 校验与退役卡', () => {
  it('choice 选项不足或答案不在其中会报问题', () => {
    const bad: QuestionBank = {
      subject: 'z', version: '0.1',
      points: [{ id: 'p', title: 't', prereq: [] }],
      items: [{ id: 'z-1', point_id: 'p', level: 1, type: 'choice', prompt: 'q', answer: 'X', options: ['A', 'A'] }],
    }
    const issues = validateBank(bad).map(i => i.message).join('|')
    expect(issues).toContain('选项少于 3')
    expect(issues).toContain('答案不在选项里')
    expect(issues).toContain('选项有重复')
  })

  it('oral / project rubric 需 3–5 条', () => {
    const bad: QuestionBank = {
      subject: 'z', version: '0.1',
      points: [{ id: 'p', title: 't', prereq: [] }],
      items: [{ id: 'z-2', point_id: 'p', level: 1, type: 'project', prompt: 'q', answer: '', rubric: ['a'] }],
    }
    expect(validateBank(bad).some(i => i.message.includes('3–5'))).toBe(true)
  })

  it('retired 的卡不进 activeCards，id 不变', () => {
    const bank: QuestionBank = {
      subject: 'z', version: '0.1',
      points: [{ id: 'p', title: 't', prereq: [] }],
      items: [
        { id: 'z-3', point_id: 'p', level: 1, type: 'term', prompt: 'q', answer: 'a' },
        { id: 'z-4', point_id: 'p', level: 1, type: 'term', prompt: 'q', answer: 'a', retired: true },
      ],
    }
    const active = activeCards(bank)
    expect(active.map(c => c.id)).toEqual(['z-3'])
    const parsed = parseBank(bank)
    expect(parsed.items.find(c => c.id === 'z-4')!.retired).toBe(true)
  })

  it('结构错误直接抛错', () => {
    expect(() => parseBank(null)).toThrow()
    expect(() => parseBank({ points: [], items: [] })).toThrow('subject')
    expect(() =>
      parseBank({ subject: 'z', items: [{ id: 'z-9', point_id: 'missing', level: 1, type: 'term', prompt: '', answer: '' }] })
    ).toThrow('point_id')
  })
})

describe('打包含约束：题库动态 import，layout / 首页主包不含题库', () => {
  it('bank.ts 用动态 import，不写 CODE_QUESTION_IDS', () => {
    const src = read('app/tongyun/subject/bank.ts')
    expect(src).toMatch(/import\(/)
    expect(src).not.toContain('CODE_QUESTION_IDS')
    // 不能有静态 JSON import
    expect(src).not.toMatch(/from\s+['"]\.\/content\/.*\.json['"]/)
  })

  it('布局只引 active-subject，不引 bank / 题库', () => {
    const layout = read('app/layouts/yunya.vue')
    expect(layout).toContain('@/tongyun/subject/active-subject')
    expect(layout).not.toMatch(/subject\/bank/)
    expect(layout).not.toMatch(/-v0\.1\.json/)
  })

  it('首页不引学科题库', () => {
    const home = read('app/pages/index.vue')
    expect(home).not.toMatch(/subject\/(bank|content)/)
    expect(home).not.toMatch(/-v0\.1\.json/)
  })

  it('grade.ts 不含 CODE_QUESTION_IDS', () => {
    expect(read('app/tongyun/subject/grade.ts')).not.toContain('CODE_QUESTION_IDS')
  })
})
