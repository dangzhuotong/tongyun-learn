<script setup lang="ts">
// tongyun: 设置页只留学习偏好；不再有学习服务地址/令牌（站点不依赖后端）
import { onMounted, ref } from 'vue'
import { ECDICT_ATTRIBUTION, NGSL_ATTRIBUTION } from '@/tongyun/english/wordlist'
import { getEnglishPrefs, saveEnglishPrefs, type EnglishPrefs } from '@/tongyun/english/prefs'
import { currentSyncUser, flushSyncQueue, loginSync, logoutSync } from '@/tongyun/sync/client'

definePageMeta({
  layout: 'yunya',
})

useSeoMeta({
  title: '橦云学习',
})

const prefs = ref<EnglishPrefs>(getEnglishPrefs())
const ready = ref(false)
const syncUser = ref('')
const syncPass = ref('')
const syncBusy = ref(false)
const signedIn = ref('')
const syncStatus = ref('')

onMounted(async () => {
  prefs.value = getEnglishPrefs()
  ready.value = true
  signedIn.value = (await currentSyncUser()) || ''
})

async function submitSync() {
  if (syncBusy.value) return
  syncBusy.value = true
  syncStatus.value = ''
  const password = syncPass.value
  syncPass.value = ''
  const loggedIn = await loginSync(syncUser.value, password)
  if (!loggedIn.ok) {
    syncStatus.value = loggedIn.message
    syncBusy.value = false
    return
  }
  signedIn.value = loggedIn.username
  const flushed = await flushSyncQueue()
  if (flushed.needsLogin) syncStatus.value = '登录未保持，请再试一次'
  else if (flushed.offline) syncStatus.value = '连不上同步服务，练习先留在这台浏览器'
  else syncStatus.value = `已上传，新写入 ${flushed.accepted} 条，重复 ${flushed.duplicate} 条，还剩 ${flushed.pending} 条`
  syncBusy.value = false
}

async function uploadOnly() {
  if (syncBusy.value) return
  syncBusy.value = true
  const flushed = await flushSyncQueue()
  if (flushed.needsLogin) syncStatus.value = '先登录学习库，再上传练习记录'
  else if (flushed.offline) syncStatus.value = '连不上同步服务，练习先留在这台浏览器'
  else syncStatus.value = `已上传，新写入 ${flushed.accepted} 条，重复 ${flushed.duplicate} 条，还剩 ${flushed.pending} 条`
  syncBusy.value = false
}

async function signOutSync() {
  await logoutSync()
  signedIn.value = ''
  syncStatus.value = '已退出同步。这台浏览器上的练习还在。'
}

function toggle(key: keyof EnglishPrefs, value: boolean) {
  prefs.value = saveEnglishPrefs({ [key]: value })
}
</script>

<template>
  <section class="settings">
    <p class="eyebrow">橦云学习</p>
    <h1>设置</h1>
    <p class="sub">学习偏好只存在这台浏览器。</p>

    <div v-if="ready" class="yy-card panel">
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
    </div>

    <div v-if="ready" class="yy-card panel">
      <h2>学习同步</h2>
      <p class="hint">练习先记在这台浏览器。登录后上传到学习库，沿用现有的作答表。密码只用于这一次登录，不会写进页面或本地记录。</p>
      <p v-if="signedIn" class="notice">已登录 {{ signedIn }}</p>
      <form class="sync-form" @submit.prevent="submitSync">
        <label>
          账号
          <input v-model="syncUser" autocomplete="username" data-testid="sync-user" />
        </label>
        <label>
          密码
          <input v-model="syncPass" type="password" autocomplete="current-password" data-testid="sync-pass" />
        </label>
        <div class="actions">
          <button type="submit" data-testid="sync-login" :disabled="syncBusy">登录并上传</button>
          <button type="button" data-testid="sync-upload" :disabled="syncBusy" @click="uploadOnly">只上传</button>
          <button v-if="signedIn" type="button" :disabled="syncBusy" @click="signOutSync">退出同步</button>
        </div>
      </form>
      <p v-if="syncStatus" class="notice" data-testid="sync-status">{{ syncStatus }}</p>
    </div>
    <p class="hint credit" data-testid="ngsl-credit">词表：{{ NGSL_ATTRIBUTION }} {{ ECDICT_ATTRIBUTION }}</p>
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

h2 {
  margin: 0;
  font-size: 22px;
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

.credit {
  margin-top: 18px;
}

.prefs {
  margin-top: 8px;
}

.sync-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sync-form label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 14px;
}

.sync-form input {
  padding: 10px 12px;
  border: 1px solid var(--color-item-border, #ddd);
  border-radius: 10px;
  font-size: 16px;
}

.sync-form button {
  padding: 10px 14px;
  border: 0;
  border-radius: 10px;
  background: var(--yy-matcha, #a4c48c);
  color: #fff;
  font-size: 15px;
  cursor: pointer;
}

.sync-form button:disabled {
  opacity: 0.6;
  cursor: default;
}
</style>
