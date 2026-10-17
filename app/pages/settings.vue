<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { clearLearnConfig, getLearnConfig, learnCheckAuth, saveLearnConfig } from '@/tongyun/learn-client'
import { fetchToday } from '@/tongyun/english/client'
import { getEnglishPrefs, saveEnglishPrefs, type EnglishPrefs } from '@/tongyun/english/prefs'

definePageMeta({
  layout: 'yunya',
})

useSeoMeta({
  title: '设置 · 云芽英语',
})

const url = ref('/learn/api/')
const token = ref('')
const prefs = ref<EnglishPrefs>(getEnglishPrefs())
const ready = ref(false)
const testing = ref(false)
const notice = ref('')
const noticeOk = ref(false)
const todayCount = ref<number | null>(null)

function flash(text: string, ok: boolean) {
  notice.value = text
  noticeOk.value = ok
}

onMounted(() => {
  const cfg = getLearnConfig()
  url.value = cfg.url || '/learn/api/'
  token.value = cfg.token || ''
  prefs.value = getEnglishPrefs()
  ready.value = true
  if (cfg.token) refreshCount()
})

function onSave() {
  saveLearnConfig({ url: url.value, token: token.value })
  flash('已保存，只存在这台浏览器', true)
  if (token.value.trim()) refreshCount()
  else todayCount.value = null
}

async function onTest() {
  testing.value = true
  notice.value = ''
  try {
    const today = await fetchToday({ url: url.value, token: token.value })
    if (today.ok) {
      todayCount.value = today.data?.items.length ?? 0
      flash(todayCount.value ? `连接正常，今日队列 ${todayCount.value} 项` : '连接正常，今日队列是空的', true)
      return
    }
    if (today.kind === 'bad_token' || today.kind === 'no_token') {
      flash('令牌不对', false)
      return
    }
    const auth = await learnCheckAuth({ url: url.value, token: token.value })
    if (auth.result === 'ok') {
      flash('令牌有效。今日队列接口还没有。', true)
      return
    }
    if (auth.result === 'bad_token') {
      flash('令牌不对', false)
      return
    }
    flash(today.kind === 'not_found' ? '连上了服务，还没有今日队列接口' : '连不上服务', false)
  } catch {
    flash('连不上服务', false)
  } finally {
    testing.value = false
  }
}

function onClear() {
  clearLearnConfig()
  url.value = '/learn/api/'
  token.value = ''
  todayCount.value = null
  flash('已清除', true)
}

function toggle(key: keyof EnglishPrefs, value: boolean) {
  prefs.value = saveEnglishPrefs({ [key]: value })
}

async function refreshCount() {
  const res = await fetchToday()
  todayCount.value = res.ok ? (res.data?.items.length ?? 0) : null
}
</script>

<template>
  <section class="settings">
    <p class="eyebrow">云芽英语</p>
    <h1>设置</h1>
    <p class="sub">学习服务地址和令牌沿用原来的配置。今天学几项由教练队列决定，这里不改课表。</p>

    <form v-if="ready" class="yy-card panel" @submit.prevent="onSave">
      <label class="yy-field">
        服务地址
        <input v-model="url" type="text" data-testid="service-url" placeholder="/learn/api/" autocomplete="off" spellcheck="false" />
      </label>
      <label class="yy-field">
        令牌
        <input v-model="token" type="password" data-testid="token-input" placeholder="Bearer 令牌" autocomplete="off" />
      </label>
      <p class="hint">线上默认同域 <code>/learn/api/</code>。本机联调填 <code>http://127.0.0.1:8031/</code>。</p>
      <p v-if="todayCount !== null" class="hint">教练今天排了 {{ todayCount }} 项。</p>
      <p v-if="notice" class="notice" :class="{ bad: !noticeOk }" data-testid="settings-notice">{{ notice }}</p>
      <div class="actions">
        <button type="button" class="yy-btn ghost" @click="onClear">清除</button>
        <button type="button" class="yy-btn ghost" :disabled="testing" data-testid="test-connection" @click="onTest">
          {{ testing ? '测试中…' : '测试连接' }}
        </button>
        <button type="submit" class="yy-btn" data-testid="save-settings">保存</button>
      </div>

      <div class="prefs">
        <label class="yy-check">
          <span>显示音标</span>
          <input type="checkbox" :checked="prefs.showPhonetic" @change="toggle('showPhonetic', ($event.target as HTMLInputElement).checked)" />
        </label>
        <label class="yy-check">
          <span>显示中文释义和例句译文</span>
          <input type="checkbox" :checked="prefs.showChinese" @change="toggle('showChinese', ($event.target as HTMLInputElement).checked)" />
        </label>
        <label class="yy-check">
          <span>大小写必须一致</span>
          <input type="checkbox" :checked="prefs.strictCase" @change="toggle('strictCase', ($event.target as HTMLInputElement).checked)" />
        </label>
        <label class="yy-check">
          <span>例句标点从宽</span>
          <input
            type="checkbox"
            :checked="prefs.loosePunctuation"
            @change="toggle('loosePunctuation', ($event.target as HTMLInputElement).checked)"
          />
        </label>
      </div>
      <p class="hint">敲句那一屏的中文提示会留着，不然整句没有可看的题目。上面的中文开关管词义和例句译文。</p>
    </form>
  </section>
</template>

<style scoped lang="scss">
.settings {
  padding-top: 28px;
}

.eyebrow {
  margin: 0;
  color: var(--yy-matcha);
  letter-spacing: 0.14em;
  font-size: 13px;
}

h1 {
  margin: 8px 0 0;
  font-size: 40px;
  font-weight: 650;
}

.sub,
.hint {
  color: var(--yy-ink-soft);
  line-height: 1.6;
}

.sub {
  margin: 8px 0 22px;
  max-width: 40rem;
}

.panel {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-width: 640px;
}

.hint {
  margin: 0;
  font-size: 13px;
}

.hint code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.notice {
  margin: 0;
  color: var(--yy-matcha-deep);
}

.notice.bad {
  color: var(--yy-danger);
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.prefs {
  margin-top: 8px;
}
</style>
