import type { Article, Sentence } from '../types'
import { TranslateEngine } from '../types'

export function getSentenceAllTranslateText(article: Article) {
  return article.sections
    .map(v =>
      v
        .map(s => s.translate.trim())
        .filter(v => v)
        .join(' \n')
    )
    .filter(v => v)
    .join(' \n\n')
}

export function getSentenceAllText(article: Article) {
  return article.sections
    .map(v =>
      v
        .map(s => s.text)
        .filter(v => v)
        .join('\n')
    )
    .filter(v => v)
    .join('\n\n')
}

/***
 * @desc
 * @param article 文章实体
 * @param translateEngine 翻译引擎
 * @param allShow 是否翻译完所有之后才显示
 * @param progressCb 进度回调
 * */
export async function getNetworkTranslate(
  article: Article,
  translateEngine: TranslateEngine,
  allShow: boolean = false,
  progressCb?: (val: number) => void
) {
  if (translateEngine === TranslateEngine.Baidu) {
    let isNotConfigured = false

    const callProxy = async (text: string): Promise<string> => {
      if (!text || !text.trim()) return ''
      const res = await fetch('/learn/api/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ q: text, from: 'en', to: 'zh-CN' }),
      }).catch(err => {
        throw err
      })

      if (res.status === 503) {
        isNotConfigured = true
        const err: any = new Error('NOT_CONFIGURED')
        err.statusCode = 503
        throw err
      }
      if (!res.ok) {
        throw new Error(`TRANSLATE_FAILED_${res.status}`)
      }
      const data = await res.json()
      return data?.trans_result?.[0]?.dst || ''
    }

    let total = 0
    article.sections.forEach(v => (total += v.length))

    if (!article.title && total === 0) {
      progressCb?.(100)
      return
    }

    // 翻译标题
    if (article.title && !article.titleTranslate) {
      try {
        const titleDst = await callProxy(article.title)
        if (titleDst) {
          article.titleTranslate = titleDst
        }
      } catch (e: any) {
        if (isNotConfigured || e?.statusCode === 503 || e?.message === 'NOT_CONFIGURED') {
          console.warn('[translate] 百度翻译未启用（需 /learn/api 服务端代理），跳过网络翻译')
          progressCb?.(100)
          return
        }
      }
    }

    if (total === 0) {
      progressCb?.(100)
      return
    }

    let promiseList: Promise<any>[] = []
    let retryCountMap = new Map<string, number>()

    const translateSentence = async (sentence: Sentence) => {
      try {
        const dst = await callProxy(sentence.text)
        const cb = () => {
          sentence.translate = dst
          if (!allShow) {
            article.textTranslate += sentence.translate + '\n'
          }
        }
        return cb
      } catch (e: any) {
        if (isNotConfigured || e?.statusCode === 503 || e?.message === 'NOT_CONFIGURED') {
          return null
        }
        return Promise.reject(() => translateSentence(sentence))
      }
    }

    let index = 0
    for (let i = 0; i < article.sections.length; i++) {
      let v = article.sections[i]
      for (let j = 0; j < v.length; j++) {
        let sentence = v[j]
        if (isNotConfigured) {
          console.warn('[translate] 百度翻译未启用（需 /learn/api 服务端代理），跳过网络翻译')
          progressCb?.(100)
          return
        }

        if (allShow) {
          promiseList.push(translateSentence(sentence))
        } else {
          retryCountMap.set(sentence.text, 0)
          let cb: (() => void) | null = null
          try {
            cb = await translateSentence(sentence)
          } catch (errTask: any) {
            let nextTask = errTask
            while (nextTask && (retryCountMap.get(sentence.text) || 0) < 2) {
              const currentRetries = retryCountMap.get(sentence.text) || 0
              retryCountMap.set(sentence.text, currentRetries + 1)
              try {
                cb = await nextTask()
                break
              } catch (retryErr: any) {
                nextTask = retryErr
              }
            }
          }

          if (isNotConfigured) {
            console.warn('[translate] 百度翻译未启用（需 /learn/api 服务端代理），跳过网络翻译')
            progressCb?.(100)
            return
          }

          if (cb) cb()
          index++
          if (progressCb) {
            progressCb(Math.floor((index / total) * 100))
          }
        }
      }
    }

    if (allShow && promiseList.length) {
      let progress = 0
      let timer: any = null
      if (progressCb) {
        timer = setInterval(() => {
          progress++
          if (progress > 90) {
            return clearInterval(timer)
          }
          progressCb(progress)
        }, 100)
      }

      const results = await Promise.allSettled(promiseList)
      if (timer) clearInterval(timer)

      if (isNotConfigured) {
        console.warn('[translate] 百度翻译未启用（需 /learn/api 服务端代理），跳过网络翻译')
        progressCb?.(100)
        return
      }
      for (const res of results) {
        if (res.status === 'fulfilled' && typeof res.value === 'function') {
          res.value()
        }
      }
      article.textTranslate = getSentenceAllTranslateText(article)
      progressCb?.(100)
      return
    }

    article.textTranslate = getSentenceAllTranslateText(article)
    progressCb?.(100)
  }
}
