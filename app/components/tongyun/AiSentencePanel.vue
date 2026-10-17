<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Dialog, BaseButton, Toast } from '@/base'
import { useDisableEventListener } from '@/core/hooks/event'
import {
  aiExplain,
  isLearnConfigured,
  type ExplainResponse,
  type SentenceGrammar,
} from '@/tongyun/learn-client'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    sentence: string
    context?: string
  }>(),
  {
    sentence: '',
    context: '',
  }
)

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
}>()

const router = useRouter()

// 弹窗打开时禁用文章快捷键
useDisableEventListener(() => props.modelValue)

const loading = ref(false)
const notConfigured = ref(false)
const errorMsg = ref('')
const data = ref<ExplainResponse<SentenceGrammar> | null>(null)

let abortController: AbortController | null = null

watch(
  () => [props.modelValue, props.sentence] as const,
  ([open, sentence], [oldOpen, oldSentence]) => {
    if (open) {
      if (!isLearnConfigured()) {
        notConfigured.value = true
        errorMsg.value = 'AI 功能暂不可用'
        return
      }
      if (!data.value || sentence !== oldSentence) {
        fetchGrammar()
      }
    } else {
      if (abortController) {
        abortController.abort()
        abortController = null
      }
      loading.value = false
    }
  }
)

onUnmounted(() => {
  if (abortController) {
    abortController.abort()
    abortController = null
  }
})

async function fetchGrammar() {
  if (!props.sentence) return

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
  data.value = null

  try {
    const res = await aiExplain<SentenceGrammar>(
      'sentence_grammar',
      {
        sentence: props.sentence,
        context: props.context || undefined,
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
  emit('update:modelValue', false)
  router.push('/setting?index=0')
}

async function copySentence() {
  if (!props.sentence) return
  try {
    await navigator.clipboard.writeText(props.sentence)
    Toast.success('已复制')
  } catch {
    Toast.error('复制失败')
  }
}

function getDifficultyBadge(diff?: string) {
  switch (diff) {
    case 'easy':
      return { label: '简单', class: 'bg-emerald-500/15 text-emerald-500 border-emerald-500/30' }
    case 'medium':
      return { label: '中等', class: 'bg-amber-500/15 text-amber-500 border-amber-500/30' }
    case 'hard':
      return { label: '较难', class: 'bg-rose-500/15 text-rose-500 border-rose-500/30' }
    default:
      return null
  }
}
</script>

<template>
  <Dialog
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    @close="emit('update:modelValue', false)"
    title="AI 讲解"
    padding
  >
    <div class="ai-sentence-container w-[640px] max-w-[90vw] max-h-[70vh] flex flex-col overflow-hidden text-sm">
      <div class="flex-1 overflow-y-auto pr-1 space-y-4">
        <!-- 原句与难度 -->
        <div class="p-3 rounded-lg bg-gray-500/10 border border-gray-500/20">
          <div class="flex items-center justify-between gap-2 mb-1.5">
            <span class="text-xs font-semibold opacity-70">原句</span>
            <span
              v-if="data?.content?.difficulty && getDifficultyBadge(data.content.difficulty)"
              class="px-2 py-0.5 rounded text-xs border"
              :class="getDifficultyBadge(data.content.difficulty)?.class"
            >
              难度：{{ getDifficultyBadge(data.content.difficulty)?.label }}
            </span>
          </div>
          <div class="text-base font-serif leading-relaxed">
            {{ sentence }}
          </div>
          <div v-if="data?.content?.translation" class="mt-2 text-sm opacity-90 leading-relaxed pt-2 border-t border-gray-500/20">
            <span class="text-xs opacity-70 block mb-0.5">翻译</span>
            {{ data.content.translation }}
          </div>
        </div>

        <!-- 还没配置提示 -->
        <div v-if="notConfigured" class="py-6 text-center text-xs text-gray-500 flex flex-col items-center gap-3">
          <span>AI 功能暂不可用</span>
        </div>

        <!-- 加载中 -->
        <div v-else-if="loading" class="py-8 text-center text-sm text-gray-500 flex items-center justify-center gap-2">
          <span>AI 分析中…</span>
        </div>

        <!-- 错误提示 -->
        <div v-else-if="errorMsg" class="py-6 text-center text-xs text-red-400 flex flex-col items-center gap-3">
          <span>{{ errorMsg }}</span>
          <BaseButton size="small" type="info" @click="fetchGrammar">重试</BaseButton>
        </div>

        <!-- 详细解析内容 -->
        <template v-else-if="data?.content">
          <!-- 句子结构 -->
          <div v-if="data.content.structure?.length" class="space-y-1.5">
            <div class="text-xs font-semibold opacity-70">句子结构</div>
            <div class="rounded-lg overflow-hidden border border-gray-500/20">
              <div
                v-for="(st, idx) in data.content.structure"
                :key="idx"
                class="flex flex-col sm:flex-row p-2 text-xs gap-1 sm:gap-3 border-b border-gray-500/10 last:border-b-0 hover:bg-gray-500/5"
              >
                <div class="font-mono sm:w-1/3 shrink-0">{{ st.text }}</div>
                <div class="font-semibold text-blue-500 sm:w-1/4 shrink-0">{{ st.role }}</div>
                <div class="text-gray-500 flex-1">{{ st.explain }}</div>
              </div>
            </div>
          </div>

          <!-- 语法点 -->
          <div v-if="data.content.grammar_points?.length" class="space-y-1.5">
            <div class="text-xs font-semibold opacity-70">语法点</div>
            <div class="space-y-2">
              <div
                v-for="(gp, idx) in data.content.grammar_points"
                :key="idx"
                class="p-2.5 rounded bg-gray-500/10 border border-gray-500/20 text-xs"
              >
                <div class="font-semibold text-amber-600 mb-1">{{ gp.name }}</div>
                <div class="opacity-90 leading-relaxed">{{ gp.explain }}</div>
              </div>
            </div>
          </div>

          <!-- 重点词 -->
          <div v-if="data.content.key_words?.length" class="space-y-1.5">
            <div class="text-xs font-semibold opacity-70">重点词</div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <div
                v-for="(kw, idx) in data.content.key_words"
                :key="idx"
                class="p-2 rounded bg-gray-500/10 border border-gray-500/20 text-xs flex flex-col gap-0.5"
              >
                <div class="flex items-center gap-2">
                  <span class="font-bold">{{ kw.word }}</span>
                  <span v-if="kw.pos" class="opacity-60 italic text-[11px]">{{ kw.pos }}</span>
                  <span class="opacity-90">{{ kw.cn }}</span>
                </div>
                <div v-if="kw.note" class="text-gray-500 text-[11px] mt-0.5">
                  {{ kw.note }}
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- 底部栏 -->
      <div class="pt-3 border-t border-gray-500/20 flex items-center justify-between mt-2 shrink-0">
        <div class="text-[11px] text-gray-500">
          <span v-if="data?.model">{{ data.model }}</span>
          <span v-if="data?.model && data?.cached"> · </span>
          <span v-if="data?.cached">缓存</span>
        </div>
        <BaseButton size="small" type="info" @click="copySentence">复制原句</BaseButton>
      </div>
    </div>
  </Dialog>
</template>

<style scoped lang="scss">
.ai-sentence-container {
  width: 640px;
}
</style>
