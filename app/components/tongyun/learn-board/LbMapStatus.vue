<!-- tongyun: 学习看板首屏的地图状态（Java / 英语），不展开整张地图 -->
<script setup lang="ts">
import { computed } from 'vue'
import type { MapStatusSummary } from '@/tongyun/learn-board-glance'
import { mapProgressLine, mapStatusLine } from '@/tongyun/learn-board-glance'

interface Props {
  summary: MapStatusSummary | null
  subjectId?: string
  subjectTitle?: string
  missingText?: string
}

const props = withDefaults(defineProps<Props>(), {
  subjectId: '',
  subjectTitle: '',
  missingText: '',
})

const headline = computed(() => (props.summary ? mapStatusLine(props.summary) : ''))
const progress = computed(() => (props.summary ? mapProgressLine(props.summary) : ''))
const visibleCounts = computed(() => {
  const counts = props.summary?.counts || []
  const nonzero = counts.filter(c => c.count > 0)
  return nonzero.length > 0 ? nonzero : counts.slice(0, 4)
})
</script>

<template>
  <div class="lb-map-status">
    <p v-if="missingText" class="lb-map-missing">{{ missingText }}</p>

    <template v-else-if="summary">
      <p v-if="subjectTitle || subjectId" class="lb-map-id">
        <span v-if="subjectTitle">{{ subjectTitle }}</span>
        <span v-if="subjectId" class="lb-map-id-code">{{ subjectId }}</span>
      </p>
      <p class="lb-map-headline">{{ headline }}</p>
      <p class="lb-map-progress">{{ progress }}</p>
      <div class="lb-map-counts">
        <span
          v-for="item in visibleCounts"
          :key="item.key"
          class="lb-map-count"
          :class="{ 'is-zero': item.count === 0 }"
        >
          <i class="lb-map-dot" :style="{ backgroundColor: item.color }" />
          {{ item.label }} {{ item.count }}
        </span>
      </div>
    </template>
  </div>
</template>

<style scoped lang="scss">
.lb-map-status {
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: var(--color-main-text);
  word-break: break-word;
}

.lb-map-missing {
  margin: 0;
  font-size: 15px;
  color: var(--color-sub-text);
}

.lb-map-id {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 14px;
  color: var(--color-sub-text);
}

.lb-map-id-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  padding: 2px 6px;
  border-radius: 6px;
  background: var(--color-second);
  border: 1px solid var(--color-item-border);
  color: var(--color-main-text);
}

.lb-map-headline {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.35;
  color: var(--color-main-text);
}

.lb-map-progress {
  margin: 0;
  font-size: 14px;
  color: var(--color-sub-text);
}

.lb-map-counts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.lb-map-count {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 13px;
  background: var(--color-second);
  border: 1px solid var(--color-item-border);

  &.is-zero {
    opacity: 0.45;
  }
}

.lb-map-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
</style>
