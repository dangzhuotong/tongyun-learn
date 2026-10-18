// tongyun: 英语手敲显示偏好。只影响呈现和判分松紧，不决定今天练什么。

export interface EnglishPrefs {
  showPhonetic: boolean
  showChinese: boolean
  strictCase: boolean
  loosePunctuation: boolean
}

export const DEFAULT_ENGLISH_PREFS: EnglishPrefs = {
  showPhonetic: true,
  showChinese: true,
  strictCase: false,
  loosePunctuation: true,
}

const STORAGE_KEY = 'tongyun-en-prefs'

function normalize(raw: unknown): EnglishPrefs {
  const saved = raw && typeof raw === 'object' ? (raw as Partial<EnglishPrefs>) : {}
  return {
    showPhonetic: saved.showPhonetic !== false,
    showChinese: saved.showChinese !== false,
    strictCase: saved.strictCase === true,
    loosePunctuation: saved.loosePunctuation !== false,
  }
}

export function getEnglishPrefs(): EnglishPrefs {
  if (typeof window === 'undefined') return { ...DEFAULT_ENGLISH_PREFS }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_ENGLISH_PREFS }
    return normalize(JSON.parse(raw))
  } catch {
    return { ...DEFAULT_ENGLISH_PREFS }
  }
}

export function saveEnglishPrefs(partial: Partial<EnglishPrefs>): EnglishPrefs {
  const next = { ...getEnglishPrefs(), ...partial }
  if (typeof window !== 'undefined') {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  }
  return next
}
