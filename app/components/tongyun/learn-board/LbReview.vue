<!-- tongyun: 学习看板组件（只读） -->
<script setup lang="ts">
import { computed } from 'vue'
import type { ReviewDueResp } from '@/tongyun/learn-board-api'

interface Props {
  data: ReviewDueResp
}

const props = defineProps<Props>()

const dueTotal = computed(() => {
  return props.data?.counts?.due_total ?? 0
})

const reviewList = computed(() => props.data?.review || [])
const newList = computed(() => props.data?.new || [])

const hasCards = computed(() => {
  return reviewList.value.length > 0 || newList.value.length > 0
})
</script>

<template>
  <div class="lb-review">
    <div class="lb-review-total-box">
      <span class="lb-review-total-num">{{ dueTotal }}</span>
      <span class="lb-review-total-label">张待复习</span>
    </div>

    <div v-if="!hasCards && dueTotal === 0" class="lb-review-empty">
      暂无待复习卡片
    </div>

    <div v-else class="lb-review-list">
      <!-- review 卡片 -->
      <div
        v-for="item in reviewList"
        :key="'rev-' + item.card_id"
        class="lb-card-item"
      >
        <span class="lb-badge lb-badge-review">复习</span>
        <div class="lb-card-front line-clamp-2">
          {{ item.front }}
        </div>
      </div>

      <!-- new 卡片 -->
      <div
        v-for="item in newList"
        :key="'new-' + item.card_id"
        class="lb-card-item"
      >
        <span class="lb-badge lb-badge-new">新卡</span>
        <div class="lb-card-front line-clamp-2">
          {{ item.front }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.lb-review {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
  color: var(--color-main-text);
  word-break: break-word;
  overflow-wrap: anywhere;
}

.lb-review-total-box {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 4px 0;
}

.lb-review-total-num {
  font-size: 32px;
  font-weight: 700;
  line-height: 1;
  color: var(--color-select-bg);
}

.lb-review-total-label {
  font-size: 15px;
  color: var(--color-sub-text);
}

.lb-review-empty {
  padding: 20px 12px;
  text-align: center;
  font-size: 15px;
  color: var(--color-sub-text);
}

.lb-review-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.lb-card-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--color-second);
  border: 1px solid var(--color-item-border);
}

.lb-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 7px;
  border-radius: 6px;
  font-size: 13px;
  flex-shrink: 0;
  margin-top: 2px;
}

.lb-badge-review {
  background: rgba(59, 130, 246, 0.15);
  color: #2563eb;
  border: 1px solid rgba(59, 130, 246, 0.4);
}

.lb-badge-new {
  background: rgba(34, 197, 94, 0.15);
  color: #16a34a;
  border: 1px solid rgba(34, 197, 94, 0.4);
}

.lb-card-front {
  flex: 1;
  font-size: 15px;
  line-height: 1.5;
  color: var(--color-main-text);
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}
</style>
