// https://nuxt.com/docs/api/configuration/nuxt-config
//@ts-ignore
import { resolve } from 'pathe'
import Icons from 'unplugin-icons/vite'
import Components from 'unplugin-vue-components/vite'
import IconsResolver from 'unplugin-icons/resolver'
import { execSync } from 'child_process'
import { defineNuxtConfig } from 'nuxt/config'

let latestCommitHash = ''
let latestCommitTime = ''
try {
  latestCommitHash = execSync('git rev-parse --short HEAD').toString().trim()
  latestCommitTime = execSync('git log -1 --format=%ci').toString().trim()
} catch (e) {
  latestCommitHash = 'unknown'
  latestCommitTime = 'unknown'
}

const siteOrigin = (process.env.ORIGIN || 'https://typewords.cc').replace(/\/$/, '')

function normalizeBaseURL(baseURL: string = '/') {
  if (!baseURL) return '/'

  let normalizedBaseURL = baseURL.trim()

  if (!normalizedBaseURL.startsWith('/')) {
    normalizedBaseURL = `/${normalizedBaseURL}`
  }
  if (!normalizedBaseURL.endsWith('/')) {
    normalizedBaseURL = `${normalizedBaseURL}/`
  }

  return normalizedBaseURL.replace(/\/{2,}/g, '/')
}

function withBaseURL(path: string, baseURL: string) {
  if (!path.startsWith('/')) return path
  if (baseURL === '/') return path
  if (path === '/') return baseURL
  return `${baseURL.slice(0, -1)}${path}`
}

function toSiteURL(path: string, baseURL: string) {
  return new URL(withBaseURL(path, baseURL), siteOrigin).toString()
}

const appBaseURL = normalizeBaseURL(process.env.NUXT_APP_BASE_URL || '/')

export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },
  app: {
    baseURL: appBaseURL,
    // keepalive: true,
    head: {
      title: '云芽英语', // tongyun: 站点入口是今日手敲
      htmlAttrs: {
        lang: 'zh-CN',
      },
      // tongyun: 官方主标「云芽」。奶茶 #FDC89C、云 #FCF4E1、芽 #A4C48C。
      // SVG 与 PNG 取自 tongyun-scaffold/brand；favicon.ico 由 yunya-512.png 缩小生成。
      // withBaseURL 避免子路径部署时图标 404。
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: withBaseURL('/yunya-mark.svg', appBaseURL) },
        { rel: 'icon', type: 'image/png', sizes: '48x48', href: withBaseURL('/favicon-48.png', appBaseURL) },
        { rel: 'icon', type: 'image/png', sizes: '96x96', href: withBaseURL('/favicon-96.png', appBaseURL) },
        { rel: 'icon', type: 'image/png', sizes: '512x512', href: withBaseURL('/yunya-512.png', appBaseURL) },
        { rel: 'apple-touch-icon', sizes: '180x180', href: withBaseURL('/favicon-180.png', appBaseURL) },
        { rel: 'icon', type: 'image/x-icon', href: withBaseURL('/favicon.ico', appBaseURL) },
      ],
    },
  },
  // ssr: false,
  routeRules: {
    '/': { ssr: false }, // tongyun: 今日
    '/practice': { ssr: false },
    '/coach': { ssr: false },
    '/settings': { ssr: false },
    '/words': { ssr: false },
    '/typewords': { prerender: true }, // tongyun: 旧入口，生成时写成跳到 /practice
    '/articles': { ssr: false },
    '/setting': { ssr: false },
    '/learn-board': { ssr: false }, // tongyun: 学习看板，纯客户端，静态产物不含数据
    '/ai-quiz': { ssr: false }, // tongyun: AI 错词复习卷，纯客户端
    '/book/nce1': { prerender: true },
    '/book/nce2': { prerender: true },
    '/book/nce3': { prerender: true },
    '/book/nce4': { prerender: true },
  },
  vite: {
    plugins: [
      Components({
        resolvers: [
          IconsResolver({
            prefix: 'Icon',
          }),
        ],
      }),
      Icons({
        autoInstall: true,
      }),
    ],
  },
  // 模块
  modules: ['@pinia/nuxt', '@unocss/nuxt', 'unplugin-icons/nuxt', '@vue-macros/nuxt', '@nuxtjs/i18n', '@nuxt/image'],
  // tongyun: 配置静态站自定义图片 provider，为运行时图片补齐 baseURL 避免 404
  image: {
    provider: 'tongyunStatic',
    providers: {
      tongyunStatic: {
        provider: '~/providers/tongyun-static.ts',
      },
    },
  },
  macros: {
    betterDefine: false,
  },
  // i18n 配置
  i18n: {
    locales: [
      { code: 'en', language: 'en-US', file: 'en.json', name: 'English' },
      { code: 'zh', language: 'zh-CN', file: 'zh.json', name: '中文' },
      { code: 'es', language: 'es-ES', file: 'es.json', name: 'Español' },
      { code: 'fr', language: 'fr-FR', file: 'fr.json', name: 'Français' },
      { code: 'pt', language: 'pt-BR', file: 'pt.json', name: 'Português' },
      { code: 'de', language: 'de-DE', file: 'de.json', name: 'Deutsch' },
      { code: 'ru', language: 'ru-RU', file: 'ru.json', name: 'Русский' },
      { code: 'uk', language: 'uk-UA', file: 'uk.json', name: 'Українська' },
      { code: 'ja', language: 'ja-JP', file: 'ja.json', name: '日本語' },
      { code: 'ko', language: 'ko-KR', file: 'ko.json', name: '한국어' },
      { code: 'th', language: 'th-TH', file: 'th.json', name: 'ไทย' },
      { code: 'vi', language: 'vi-VN', file: 'vi.json', name: 'Tiếng Việt' },
      { code: 'id', language: 'id-ID', file: 'id.json', name: 'Bahasa Indonesia' },
      { code: 'tw', language: 'zh-TW', file: 'tw.json', name: '繁體中文' },
    ],
    defaultLocale: 'zh',
    // langDir:'app/i18n/',
    strategy: 'no_prefix',
  },
  // CSS
  css: ['~/assets/css/main.scss'],
  // 别名配置
  alias: {
    '@': resolve(__dirname, 'app'),
  },
  // 自动导入配置
  imports: {
    dirs: ['app/composables/**', 'app/utils/**'],
  },
  // 组件自动导入目录
  components: [
    { path: 'components', pathPrefix: false },
    { path: 'app/components', pathPrefix: false },
  ],
  // 运行时配置
  runtimeConfig: {
    public: {
      apiBase: process.env.API_BASE || 'http://localhost/',
      origin: process.env.ORIGIN || 'https://typewords.cc',
      host: process.env.HOST || 'typewords.cc',
      passwordRsaPublicKey: process.env.VITE_PASSWORD_RSA_PUBLIC_KEY || '',
      latestCommitHash: latestCommitHash + (process.env.NODE_ENV === 'production' ? '' : ' (dev)'),
      latestCommitTime: latestCommitTime,
    },
  },
  // 构建配置
  build: {
    transpile: ['vue-virtual-scroller', 'vxe-table'],
  },
  // 实验性功能
  experimental: {
    payloadExtraction: false, // 禁用 payload 提取，减少构建体积
  },
  // TypeScript 配置
  typescript: {
    strict: false,
    typeCheck: false, // 构建时不进行类型检查，加快构建速度
    tsConfig: {
      compilerOptions: {
        types: ['vue-macros/macros-global'],
        allowImportingTsExtensions: true,
      },
    },
  },
  devServer: {
    port: 5567,
  },
  nitro: {
    prerender: {
      ignore: appBaseURL === '/' ? [] : [withBaseURL('/manifest.json', appBaseURL)],
      // tongyun: 云芽四页和旧 /typewords 都要进静态产物
      routes: ['/practice', '/coach', '/settings', '/typewords'],
    },
    devProxy: {
      '/baidu': {
        target: 'https://api.fanyi.baidu.com/api/trans/vip/translate',
        changeOrigin: true,
      },
    },
  },
})
