import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { getNetworkTranslate, getSentenceAllText, getSentenceAllTranslateText } from './translate'
import { TranslateEngine } from '../types'
import type { Article, Sentence } from '../types'

function createSampleArticle(): Article {
  const sentence1: Sentence = {
    text: 'Hello world.',
    translate: '',
    words: [],
    audioPosition: [0, 1],
  }
  const sentence2: Sentence = {
    text: 'Nice to meet you.',
    translate: '',
    words: [],
    audioPosition: [1, 2],
  }

  return {
    title: 'Greetings',
    titleTranslate: '',
    text: 'Hello world.\nNice to meet you.',
    textTranslate: '',
    newWords: [],
    sections: [[sentence1], [sentence2]],
    audioSrc: '',
    audioFileId: '',
  }
}

describe('app/core/hooks/translate', () => {
  const originalFetch = globalThis.fetch
  let warnSpy: any

  beforeEach(() => {
    vi.restoreAllMocks()
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('degrades gracefully without throwing when translate proxy returns 503 (not configured)', async () => {
    globalThis.fetch = vi.fn().mockImplementation(async () => ({
      ok: false,
      status: 503,
      json: async () => ({
        statusCode: 503,
        message: 'Baidu translate service not configured',
      }),
    })) as any

    const article = createSampleArticle()
    const progressList: number[] = []

    await expect(
      getNetworkTranslate(article, TranslateEngine.Baidu, false, val => progressList.push(val))
    ).resolves.toBeUndefined()

    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('[translate] 百度翻译未启用（需 /learn/api 服务端代理），跳过网络翻译')
    )
    expect(progressList).toContain(100)
    expect(article.titleTranslate).toBe('')
    expect(article.sections[0][0].translate).toBe('')
  })

  it('translates title and sentences correctly when translate proxy succeeds', async () => {
    globalThis.fetch = vi.fn().mockImplementation(async (url: string, opts: any) => {
      const body = JSON.parse(opts.body)
      let dst = ''
      if (body.q === 'Greetings') dst = '问候'
      else if (body.q === 'Hello world.') dst = '你好世界。'
      else if (body.q === 'Nice to meet you.') dst = '很高兴见到你。'
      else dst = `translated: ${body.q}`

      return {
        ok: true,
        status: 200,
        json: async () => ({
          from: 'en',
          to: 'zh',
          trans_result: [{ src: body.q, dst }],
        }),
      }
    }) as any

    const article = createSampleArticle()
    const progressList: number[] = []

    await getNetworkTranslate(article, TranslateEngine.Baidu, false, val => progressList.push(val))

    expect(article.titleTranslate).toBe('问候')
    expect(article.sections[0][0].translate).toBe('你好世界。')
    expect(article.sections[1][0].translate).toBe('很高兴见到你。')
    expect(article.textTranslate).toContain('你好世界。')
    expect(article.textTranslate).toContain('很高兴见到你。')
    expect(progressList[progressList.length - 1]).toBe(100)
  })

  it('handles empty article without error', async () => {
    const emptyArticle: Article = {
      title: '',
      titleTranslate: '',
      text: '',
      textTranslate: '',
      newWords: [],
      sections: [],
      audioSrc: '',
      audioFileId: '',
    }

    const progressList: number[] = []
    await getNetworkTranslate(emptyArticle, TranslateEngine.Baidu, false, val => progressList.push(val))
    expect(progressList).toContain(100)
  })

  it('getSentenceAllText and getSentenceAllTranslateText format text properly', () => {
    const article = createSampleArticle()
    article.sections[0][0].translate = '你好世界。'
    article.sections[1][0].translate = '很高兴见到你。'

    const allText = getSentenceAllText(article)
    expect(allText).toBe('Hello world.\n\nNice to meet you.')

    const allTrans = getSentenceAllTranslateText(article)
    expect(allTrans).toBe('你好世界。 \n\n很高兴见到你。')
  })
})
