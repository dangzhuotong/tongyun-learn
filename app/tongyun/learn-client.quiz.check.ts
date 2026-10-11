// tongyun: 纯函数自检（不调网络）
import { gradeQuizAnswer, pickWrongWordsForQuiz } from './learn-client.ts'

const errors: string[] = []

function assert(cond: boolean, msg: string) {
  if (!cond) errors.push(msg)
}

const words = [
  { word: 'Abandon', trans: [{ cn: '放弃' }] },
  { word: 'abandon', trans: [{ cn: '抛弃' }] },
  { word: 'ability', trans: [{ cn: '能力' }] },
  ...Array.from({ length: 25 }, (_, i) => ({
    word: `w${i}`,
    trans: [{ cn: `义${i}` }],
  })),
]

const picked = pickWrongWordsForQuiz(words, 20)
assert(picked.length === 20, `期望 20，实际 ${picked.length}`)
assert(picked[0].word === 'Abandon', `首词应为 Abandon，实际 ${picked[0]?.word}`)
assert(picked[0].cn === '放弃', `首词 cn 应为 放弃`)
assert(!picked.some((w, i) => i > 0 && w.word.toLowerCase() === 'abandon'), 'abandon 应去重')

assert(gradeQuizAnswer('  Abandon ', 'abandon') === true, 'cloze 大小写不敏感应判对')
assert(gradeQuizAnswer('ability', 'abandon') === false, '错误答案应判错')
assert(gradeQuizAnswer('', 'abandon') === false, '空输入应判错')

// tongyun: en2zh 多释义与标点容错测试
assert(gradeQuizAnswer('放弃', '放弃；抛弃') === true, '分号多释义命中其一应判对')
assert(gradeQuizAnswer('抛弃', '放弃，抛弃') === true, '逗号多释义命中其一应判对')
assert(gradeQuizAnswer('放弃', '放弃。') === true, '末尾带句号应判对')
assert(gradeQuizAnswer('坚持', '放弃；抛弃') === false, '非相关释义应判错')

// tongyun: 脏词过滤与超长截断测试（服务端 QuizWordItem 契约）
const dirtyWords = [
  { word: '12345', trans: [{ cn: '纯数字' }] },
  { word: '纯中文', trans: [{ cn: '无英文' }] },
  { word: 'a'.repeat(65), trans: [{ cn: '超过64位' }] },
  { word: 'valid', trans: [{ cn: 'x'.repeat(150) }] },
]
const cleanedDirty = pickWrongWordsForQuiz(dirtyWords, 20)
assert(cleanedDirty.length === 1, `应只保留 1 个合规词，实际 ${cleanedDirty.length}`)
assert(cleanedDirty[0].word === 'valid', `合规词应为 valid`)
assert(cleanedDirty[0].cn?.length === 100, `超长 cn 应截断至 100 字符，实际 ${cleanedDirty[0].cn?.length}`)

if (errors.length) {
  console.error('FAIL')
  for (const e of errors) console.error('-', e)
  process.exit(1)
}
console.log('PASS learn-client.quiz.check.ts')
