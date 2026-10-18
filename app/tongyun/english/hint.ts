// tongyun: 随机拼写提示。每次出题随机露出约 30% 字母（至少 1 个），其余用 _ 占位。
// 第 1 次复习拼写、以及第 2 次起拼错时都用它。纯函数，方便测试。

export interface HintMask {
  /** 被露出的字母位置（原词下标） */
  positions: number[]
  /** 这个词一共有几个字母（长度，空格不计） */
  letters: number
}

const LETTER = /[A-Za-z]/

/** 返回该词所有字母的位置 */
export function letterPositions(word: string): number[] {
  const out: number[] = []
  for (let i = 0; i < word.length; i += 1) if (LETTER.test(word[i]!)) out.push(i)
  return out
}

/**
 * 随机提示：露出约 30% 的字母，至少 1 个。
 * 传入 rng 便于测试（默认 Math.random）。
 */
export function randomHint(word: string, rng: () => number = Math.random): HintMask {
  const all = letterPositions(word)
  const letters = all.length
  if (!letters) return { positions: [], letters: 0 }
  const reveal = Math.min(all.length, Math.max(1, Math.round(letters * 0.3)))
  const pool = all.slice()
  for (let i = pool.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1))
    ;[pool[i], pool[j]] = [pool[j]!, pool[i]!]
  }
  const positions = pool.slice(0, reveal).sort((a, b) => a - b)
  return { positions, letters }
}

/** 把提示渲染成等下敲的样子：露出的字母保留，其余字母变 _，空格和符号原样。 */
export function hintText(word: string, mask: HintMask): string {
  const revealed = new Set(mask.positions)
  const chars = [...word]
  return chars.map((ch, i) => (LETTER.test(ch) ? (revealed.has(i) ? ch : '_') : ch)).join('')
}
