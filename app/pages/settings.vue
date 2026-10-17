<script setup lang="ts">
// tongyun: 设置页只留学习偏好；不再有学习服务地址/令牌（站点不依赖后端）
import { onMounted, ref } from 'vue'
import { getEnglishPrefs, saveEnglishPrefs, type EnglishPrefs } from '@/tongyun/english/prefs'

definePageMeta({
  layout: 'yunya',
})

useSeoMeta({
  title: '橦云学习',
})

const prefs = ref<EnglishPrefs>(getEnglishPrefs())
const ready = ref(false)

onMounted(() => {
  prefs.value = getEnglishPrefs()
  ready.value = true
})

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
