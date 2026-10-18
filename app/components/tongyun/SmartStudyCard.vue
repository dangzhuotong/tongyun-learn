<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useBaseStore } from '@/core/stores/base.ts'
import { BaseButton } from '@/base'
import { createSmartTask, isSmartStudyActive, type SmartTaskResult } from '@/ai/smart-task'

const props = withDefaults(
  defineProps<{
    disabled?: boolean
    hasSavedTask?: boolean
  }>(),
  {
    disabled: false,
    hasSavedTask: false,
  }
)

const emit = defineEmits<{
  (e: 'start'): void
}>()

const loading = ref(true)
const task = ref<SmartTaskResult | null>(null)

const isContinue = computed(() => {
  return isSmartStudyActive() && props.hasSavedTask
})

const buttonText = computed(() => {
  return isContinue.value ? '继续智能混学' : '开始智能混学'
})

const reviewDisplayText = computed(() => {
  if (!task.value) return '0'
  const m = task.value.taskWords.review.length
  const due = task.value.dueCount
  if (due > m) {
    return `${m} / 到期共 ${due}`
  }
  return String(m)
})

const isZeroWords = computed(() => {
  if (loading.value || !task.value) return false
  return task.value.taskWords.new.length === 0 && task.value.taskWords.review.length === 0
})

const isButtonDisabled = computed(() => {
  if (props.disabled) return true
  if (loading.value) return true
  if (!isContinue.value && isZeroWords.value) return true
  return false
})

const zeroWordsTip = '暂无可学的词，先添加词书'

const store = useBaseStore()

async function refresh() {
  loading.value = true
  try {
    task.value = await createSmartTask()
  } catch (e) {
    console.error('[SmartStudyCard] Failed to create smart task:', e)
  } finally {
    loading.value = false
  }
}

// 等本地数据（IndexedDB）加载完再统计，否则词书列表还是空的
watch(
  () => store.load,
  loaded => {
    if (loaded) refresh()
  },
  { immediate: true }
)
</script>

<template>
  <div class="card">
    <div class="flex items-center justify-between">
      <div>
        <div class="flex items-center gap-2">
          <div class="p-2 center rounded-full bg-white">
            <IconFluentSparkle20Regular class="text-lg color-amber" />
          </div>
          <div class="text-xl font-bold">智能混学</div>
          <span v-if="loading" class="text-xs text-gray-400">统计中…</span>
        </div>
        <div class="text-xs text-gray-500 mt-1">
          不分章节：所有词书里到期的词按记忆曲线复习，新词从没学过的词里随机抽
        </div>
      </div>
    </div>

    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
      <div class="stat">
        <div class="num" :class="loading && 'loading-num'">
          {{ loading ? '统计中…' : (task?.taskWords.new.length ?? 0) }}
        </div>
        <div class="txt">今日新词</div>
      </div>
      <div class="stat">
        <div class="num" :class="[loading ? 'loading-num' : 'text-2xl md:text-3xl break-keep']">
          {{ loading ? '统计中…' : reviewDisplayText }}
        </div>
        <div class="txt">到期复习</div>
      </div>
      <div class="stat">
        <div class="num" :class="loading && 'loading-num'">
          {{ loading ? '统计中…' : `${task?.bookCount ?? 0} 本` }}
        </div>
        <div class="txt">覆盖词书</div>
      </div>
      <div class="stat">
        <div class="num" :class="loading && 'loading-num'">
          {{ loading ? '统计中…' : (task?.newPoolCount ?? 0) }}
        </div>
        <div class="txt">未学词池</div>
      </div>
    </div>

    <div class="flex items-center mt-4 gap-4 flex-wrap">
      <BaseButton
        size="large"
        type="primary"
        :disabled="isButtonDisabled"
        :loading="loading"
        :title="!isContinue && isZeroWords ? zeroWordsTip : ''"
        @click="emit('start')"
      >
        <div class="flex items-center gap-2">
          <span class="line-height-[2]">{{ buttonText }}</span>
          <IconFluentArrowCircleRight16Regular class="text-xl" />
        </div>
      </BaseButton>
      <span v-if="!loading && !isContinue && isZeroWords" class="text-sm text-gray-400">
        {{ zeroWordsTip }}
      </span>
    </div>
  </div>
</template>

<style scoped lang="scss">
.stat {
  @apply box-border flex flex-col items-center justify-center rounded-xl p-3 bg-[var(--bg-history)];
  border: 1px solid gainsboro;

  .num {
    @apply color-[#409eff] text-3xl font-bold;
  }

  .txt {
    @apply color-gray-500 text-sm mt-1;
  }
}

.loading-num {
  @apply text-base font-normal text-gray-400;
}
</style>
