<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import type { Word } from '@/core/types/types.ts'
import { BaseButton } from '@/base'
import {
  aiExplain,
  isLearnConfigured,
  type ExplainResponse,
  type WordMnemonic,
} from '@/tongyun/learn-client'

const props = defineProps<{
  word: Word
}>()

const router = useRouter()

const isOpen = ref(false)
const loading = ref(false)
const notConfigured = ref(false)
const errorMsg = ref('')
const data = ref<ExplainResponse<WordMnemonic> | null>(null)

let abortController: AbortController | null = null

function reset() {
  if (abortController) {
    abortController.abort()
    abortController = null
  }
  isOpen.value = false
  loading.value = false
  notConfigured.value = false
  errorMsg.value = ''
  data.value = null
}

watch(
  () => props.word?.word,
  () => {
    reset()
  }
)

onUnmounted(() => {
  if (abortController) {
    abortController.abort()
    abortController = null
  }
})

function toggle() {
  if (isOpen.value) {
    isOpen.value = false
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    loading.value = false
    return
  }

  isOpen.value = true
  if (!isLearnConfigured()) {
    notConfigured.value = true
    errorMsg.value = 'AI 功能暂不可用'
    return
  }

  if (!data.value) {
    fetchMnemonic()
  }
}

async function fetchMnemonic() {
  if (!isLearnConfigured()) {
    notConfigured.value = true
    errorMsg.value = 'AI 功能暂不可用'
    return
  }

  if (abortController) {
    abortController.abort()
  }
  abortController = new AbortController()

  loading.value = true
  errorMsg.value = ''
  notConfigured.value = false

  const context = (props.word.trans || [])
    .slice(0, 3)
    .map(t => `${t.pos ? t.pos + ' ' : ''}${t.cn || ''}`.trim())
    .filter(Boolean)
    .join('；')
    .slice(0, 500)

  try {
    const res = await aiExplain<WordMnemonic>(
      'word_mnemonic',
      {
        word: props.word.word,
        context,
      },
      { signal: abortController.signal }
    )
    data.value = res
  } catch (err: any) {
    if (err?.name === 'AbortError') return
    if (err?.code === 'not_configured') {
      notConfigured.value = true
    }
    errorMsg.value = err?.message || '请求失败，请稍后再试'
  } finally {
    loading.value = false
  }
}

function goToSetting() {
  router.push('/setting?index=0')
}

function getRootTypeClass(type?: string) {
  switch (type) {
    case 'prefix':
      return 'bg-blue-500/15 text-blue-500 border-blue-500/30'
    case 'root':
      return 'bg-emerald-500/15 text-emerald-500 border-emerald-500/30'
    case 'suffix':
      return 'bg-purple-500/15 text-purple-500 border-purple-500/30'
    default:
      return 'bg-gray-500/15 text-gray-500 border-gray-500/30'
  }
}
</script>

<template>
  <div class="ai-word-tips text-sm">
    <div class="flex items-center gap-3">
      <div class="label font-medium opacity-80">AI 记忆法</div>
      <BaseButton size="small" type="info" @click="toggle">
        {{ isOpen ? '收起' : 'AI 记忆法' }}
      </BaseButton>
      <span v-if="loading" class="text-xs text-gray-500">AI 生成中…</span>
    </div>

    <div v-if="isOpen" class="mt-2.5">
      <!-- 还没配置提示 -->
      <div v-if="notConfigured" class="text-xs text-gray-500 flex items-center gap-2 py-1">
        <span>AI 功能暂不可用</span>
      </div>

      <!-- 错误提示 -->
      <div v-else-if="errorMsg" class="text-xs text-red-400 flex items-center gap-2 py-1">
        <span>{{ errorMsg }}</span>
        <BaseButton size="small" type="info" @click="fetchMnemonic">重试</BaseButton>
      </div>

      <!-- 结果卡片 -->
      <div
        v-else-if="data?.content"
        class="result-card flex flex-col gap-2.5 p-3 rounded-lg bg-gray-500/10 border border-gray-500/20"
      >
        <!-- 词根拆分 -->
        <div v-if="data.content.roots?.length" class="flex flex-wrap gap-2 items-center">
          <span class="text-xs opacity-70">词根拆分：</span>
          <span
            v-for="(r, idx) in data.content.roots"
            :key="idx"
            class="px-2 py-0.5 rounded text-xs border"
            :class="getRootTypeClass(r.type)"
          >
            <span class="font-semibold">{{ r.part }}</span>
            <span v-if="r.meaning" class="opacity-80"> ({{ r.meaning }})</span>
          </span>
        </div>

        <!-- 口诀 -->
        <div
          v-if="data.content.mnemonic"
          class="p-2.5 rounded text-sm bg-amber-500/10 text-amber-600 border-l-3 border-amber-500"
        >
          <div class="text-xs opacity-70 mb-0.5">口诀：</div>
          <div class="font-medium">{{ data.content.mnemonic }}</div>
        </div>

        <!-- 词源 -->
        <div v-if="data.content.etymology" class="text-xs opacity-80 leading-relaxed">
          <span class="font-medium opacity-90">词源：</span>
          <span>{{ data.content.etymology }}</span>
        </div>

        <!-- 例句 -->
        <div v-if="data.content.examples?.length" class="space-y-1.5">
          <div class="text-xs opacity-70">例句：</div>
          <div
            v-for="(ex, idx) in data.content.examples"
            :key="idx"
            class="text-xs leading-relaxed pl-2 border-l-2 border-gray-500/30"
          >
            <div class="en">{{ ex.en }}</div>
            <div class="text-gray-500">{{ ex.zh }}</div>
          </div>
        </div>

        <!-- 相关词 -->
        <div v-if="data.content.related?.length" class="flex flex-wrap gap-2 items-center text-xs">
          <span class="opacity-70">相关词：</span>
          <span
            v-for="(rel, idx) in data.content.related"
            :key="idx"
            class="bg-gray-500/10 px-2 py-0.5 rounded border border-gray-500/20"
          >
            <span class="font-medium">{{ rel.word }}</span>
            <span class="opacity-70"> — {{ rel.cn }}</span>
          </span>
        </div>

        <!-- 底部信息 -->
        <div
          v-if="data.model || data.cached"
          class="text-[11px] text-gray-500 text-right mt-0.5"
        >
          <span v-if="data.model">{{ data.model }}</span>
          <span v-if="data.model && data.cached"> · </span>
          <span v-if="data.cached">缓存</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.label {
  width: 7rem;
  padding-top: 0.2rem;
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .label {
    width: unset;
    margin-right: 0.5rem;
  }
}
</style>
