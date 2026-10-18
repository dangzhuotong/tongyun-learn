import { describe, expect, it } from 'vitest'
import {
  AI_BANK,
  DAY,
  INTERVALS,
  JAVA_BANK,
  buildSubjectSession,
  getKnowledgePoint,
  getSubjectBank,
  gradeAnswer,
  isCodeQuestion,
  nextSubjectStat,
  stripWhitespace,
  type QuestionItem,
  type SubjectItemStat,
} from './index'

const NOW = 1_800_000_000_000

describe('subject question bank loading (java-v0.1.json & ai-v0.1.json)', () => {
  it('loads Java question bank with correct version and 20 items', () => {
    expect(JAVA_BANK.subject).toBe('java')
    expect(JAVA_BANK.version).toBe('0.1')
    expect(JAVA_BANK.points.length).toBeGreaterThan(0)
    expect(JAVA_BANK.items.length).toBe(20)

    const equalsPoint = getKnowledgePoint(JAVA_BANK, 'java.object.equals-hashcode')
    expect(equalsPoint?.title).toBe('equals 与 hashCode')
  })

  it('loads AI question bank with correct version and 20 items', () => {
    expect(AI_BANK.subject).toBe('ai')
    expect(AI_BANK.version).toBe('0.1')
    expect(AI_BANK.points.length).toBeGreaterThan(0)
    expect(AI_BANK.items.length).toBe(20)

    const llmPoint = getKnowledgePoint(AI_BANK, 'ai.llm.basics')
    expect(llmPoint?.title).toBe('LLM 基础')
  })

  it('retrieves subject banks via getSubjectBank', () => {
    expect(getSubjectBank('java')).toBe(JAVA_BANK)
    expect(getSubjectBank('JAVA')).toBe(JAVA_BANK)
    expect(getSubjectBank('ai')).toBe(AI_BANK)
    expect(getSubjectBank('AI')).toBe(AI_BANK)
  })
})

describe('code question grading (ignores whitespace)', () => {
  const java0003 = JAVA_BANK.items.find(i => i.id === 'java-0003')!
  const java0015 = JAVA_BANK.items.find(i => i.id === 'java-0015')!
  const java0017 = JAVA_BANK.items.find(i => i.id === 'java-0017')!
  const ai0019 = AI_BANK.items.find(i => i.id === 'ai-0019')!

  it('identifies code questions correctly', () => {
    expect(isCodeQuestion(java0003)).toBe(true)
    expect(isCodeQuestion(java0015)).toBe(true)
    expect(isCodeQuestion(java0017)).toBe(true)
    expect(isCodeQuestion(ai0019)).toBe(true)

    const java0001 = JAVA_BANK.items.find(i => i.id === 'java-0001')!
    expect(isCodeQuestion(java0001)).toBe(false)
  })

  it('grades java-0003 ignoring whitespace', () => {
    // answer: "return Objects.hash(name, age);"
    expect(gradeAnswer('return Objects.hash(name, age);', java0003)).toBe(true)
    expect(gradeAnswer('return Objects.hash(name,age);', java0003)).toBe(true)
    expect(gradeAnswer('return   Objects.hash( name , age ) ;', java0003)).toBe(true)
    expect(gradeAnswer('Objects.hash(name, age)', java0003)).toBe(true)
    expect(gradeAnswer('Objects.hash(name,age)', java0003)).toBe(true)
    expect(gradeAnswer('Objects.hash( name , age )', java0003)).toBe(true)

    expect(gradeAnswer('return Objects.equals(name, age);', java0003)).toBe(false)
  })

  it('grades java-0015 ignoring whitespace and quotes', () => {
    // answer: "try (BufferedReader br = new BufferedReader(new FileReader(\"a.txt\"))) {"
    expect(gradeAnswer('try (BufferedReader br = new BufferedReader(new FileReader("a.txt"))) {', java0015)).toBe(true)
    expect(gradeAnswer('try(BufferedReader br = new BufferedReader(new FileReader("a.txt"))){', java0015)).toBe(true)
    expect(gradeAnswer('try(BufferedReader br=new BufferedReader(new FileReader("a.txt"))){', java0015)).toBe(true)
    expect(gradeAnswer('try ( BufferedReader br = new BufferedReader( new FileReader( "a.txt" ) ) ) {', java0015)).toBe(true)
    expect(gradeAnswer('try (BufferedReader br = new BufferedReader(new FileReader("a.txt")))', java0015)).toBe(true)

    expect(gradeAnswer('BufferedReader br = new BufferedReader(new FileReader("a.txt"))', java0015)).toBe(false)
  })

  it('grades java-0017 ignoring whitespace', () => {
    // answer: "ExecutorService pool = Executors.newFixedThreadPool(4);"
    expect(gradeAnswer('ExecutorService pool = Executors.newFixedThreadPool(4);', java0017)).toBe(true)
    expect(gradeAnswer('ExecutorService pool=Executors.newFixedThreadPool(4);', java0017)).toBe(true)
    expect(gradeAnswer('ExecutorService   pool = Executors.newFixedThreadPool( 4 );', java0017)).toBe(true)
    expect(gradeAnswer('Executors.newFixedThreadPool(4)', java0017)).toBe(true)
    expect(gradeAnswer('Executors.newFixedThreadPool( 4 )', java0017)).toBe(true)

    expect(gradeAnswer('Executors.newCachedThreadPool()', java0017)).toBe(false)
  })

  it('grades ai-0019 ignoring whitespace', () => {
    // answer: "chatClient.prompt().user(\"hi\").call().content();"
    expect(gradeAnswer('chatClient.prompt().user("hi").call().content();', ai0019)).toBe(true)
    expect(gradeAnswer('chatClient.prompt().user("hi").call().content()', ai0019)).toBe(true)
    expect(gradeAnswer('chatClient . prompt() . user( "hi" ) . call() . content() ;', ai0019)).toBe(true)
    expect(gradeAnswer('String r = chatClient.prompt().user("hi").call().content();', ai0019)).toBe(true)
    expect(gradeAnswer('String r=chatClient.prompt().user("hi").call().content();', ai0019)).toBe(true)

    expect(gradeAnswer('chatClient.prompt().user("hi").call().entity()', ai0019)).toBe(false)
  })
})

describe('non-code question grading', () => {
  it('grades java-0001 with answer and accept alternatives', () => {
    const itm = JAVA_BANK.items.find(i => i.id === 'java-0001')!
    expect(gradeAnswer('hashCode', itm)).toBe(true)
    expect(gradeAnswer('hashcode', itm)).toBe(true)
    expect(gradeAnswer('hashCode()', itm)).toBe(true)
    expect(gradeAnswer('哈希码', itm)).toBe(true)
    expect(gradeAnswer('  hashCode  ', itm)).toBe(true)
    expect(gradeAnswer('equals', itm)).toBe(false)
  })

  it('grades java-0002 with number representations', () => {
    const itm = JAVA_BANK.items.find(i => i.id === 'java-0002')!
    expect(gradeAnswer('2', itm)).toBe(true)
    expect(gradeAnswer('两个', itm)).toBe(true)
    expect(gradeAnswer('二', itm)).toBe(true)
    expect(gradeAnswer('2个', itm)).toBe(true)
    expect(gradeAnswer('1', itm)).toBe(false)
  })

  it('grades ai-0001 with token terms', () => {
    const itm = AI_BANK.items.find(i => i.id === 'ai-0001')!
    expect(gradeAnswer('token', itm)).toBe(true)
    expect(gradeAnswer('Token', itm)).toBe(true)
    expect(gradeAnswer('tokens', itm)).toBe(true)
    expect(gradeAnswer('词元', itm)).toBe(true)
    expect(gradeAnswer('character', itm)).toBe(false)
  })

  it('grades ai-0002 with context window synonyms', () => {
    const itm = AI_BANK.items.find(i => i.id === 'ai-0002')!
    expect(gradeAnswer('context window', itm)).toBe(true)
    expect(gradeAnswer('上下文窗口', itm)).toBe(true)
    expect(gradeAnswer('context length', itm)).toBe(true)
    expect(gradeAnswer('上下文长度', itm)).toBe(true)
    expect(gradeAnswer('context', itm)).toBe(true)
    expect(gradeAnswer('temperature', itm)).toBe(false)
  })

  it('grades ai-0020 with AiServices variations', () => {
    const itm = AI_BANK.items.find(i => i.id === 'ai-0020')!
    expect(gradeAnswer('AiServices', itm)).toBe(true)
    expect(gradeAnswer('AI Services', itm)).toBe(true)
    expect(gradeAnswer('aiservices', itm)).toBe(true)
    expect(gradeAnswer('AI 服务', itm)).toBe(true)
    expect(gradeAnswer('Spring AI', itm)).toBe(false)
  })
})

describe('1/3/7/14/30 spaced repetition progression and reset', () => {
  it('advances through 1, 3, 7, 14, 30 day intervals on correct answers', () => {
    // 首次作答正确：进入第 0 档（1 天）
    let s = nextSubjectStat(undefined, true, NOW)
    expect(s.box).toBe(0)
    expect(s.due - NOW).toBe(1 * DAY)
    expect(s.right).toBe(1)
    expect(s.wrong).toBe(0)

    // 第二次作答正确：进入第 1 档（3 天）
    s = nextSubjectStat(s, true, NOW)
    expect(s.box).toBe(1)
    expect(s.due - NOW).toBe(3 * DAY)
    expect(s.right).toBe(2)

    // 第三次作答正确：进入第 2 档（7 天）
    s = nextSubjectStat(s, true, NOW)
    expect(s.box).toBe(2)
    expect(s.due - NOW).toBe(7 * DAY)
    expect(s.right).toBe(3)

    // 第四次作答正确：进入第 3 档（14 天）
    s = nextSubjectStat(s, true, NOW)
    expect(s.box).toBe(3)
    expect(s.due - NOW).toBe(14 * DAY)
    expect(s.right).toBe(4)

    // 第五次作答正确：进入第 4 档（30 天）
    s = nextSubjectStat(s, true, NOW)
    expect(s.box).toBe(4)
    expect(s.due - NOW).toBe(30 * DAY)
    expect(s.right).toBe(5)

    // 第六次作答正确：最高停在第 4 档（30 天）
    s = nextSubjectStat(s, true, NOW)
    expect(s.box).toBe(4)
    expect(s.due - NOW).toBe(30 * DAY)
    expect(s.right).toBe(6)
  })

  it('resets interval back to box 0 (1 day) on wrong answer', () => {
    // 假设已到第 3 档（14 天）
    const prev: SubjectItemStat = {
      right: 4,
      wrong: 0,
      last: NOW - 14 * DAY,
      box: 3,
      due: NOW,
      first: NOW - 30 * DAY,
    }

    const wrongResult = nextSubjectStat(prev, false, NOW)
    expect(wrongResult.box).toBe(0)
    expect(wrongResult.due - NOW).toBe(1 * DAY)
    expect(wrongResult.wrong).toBe(1)
    expect(wrongResult.right).toBe(4)
    expect(wrongResult.first).toBe(prev.first)
  })
})

describe('subject practice session building', () => {
  it('schedules due items first in order of due date, then new items', () => {
    const stats: Record<string, SubjectItemStat> = {
      'java-0001': {
        right: 1,
        wrong: 0,
        last: NOW - 3 * DAY,
        box: 0,
        due: NOW - 2 * DAY, // 到期较早
        first: NOW - 3 * DAY,
      },
      'java-0002': {
        right: 2,
        wrong: 0,
        last: NOW - 2 * DAY,
        box: 1,
        due: NOW - 1 * DAY, // 到期较晚
        first: NOW - 5 * DAY,
      },
      'java-0003': {
        right: 3,
        wrong: 0,
        last: NOW - DAY,
        box: 2,
        due: NOW + 6 * DAY, // 未到期，不应进入 due
        first: NOW - 10 * DAY,
      },
    }

    const plan = buildSubjectSession(JAVA_BANK, stats, NOW, 5)
    expect(plan.dueTotal).toBe(2)
    expect(plan.items[0].id).toBe('java-0001')
    expect(plan.items[1].id).toBe('java-0002')
    // 新题排在后面
    expect(plan.items[2].id).toBe('java-0004')
    expect(plan.newTotal).toBe(5)
  })
})
