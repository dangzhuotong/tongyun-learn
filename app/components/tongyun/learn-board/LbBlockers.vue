<!-- tongyun: 学习看板组件（只读） -->
<script setup lang="ts">
import type { Blocker } from '@/tongyun/learn-board-api'

interface Props {
  items: Blocker[]
}

defineProps<Props>()

function formatDate(dateStr?: string | null): string {
  if (!dateStr) return ''
  return dateStr.slice(0, 10)
}
</script>

<template>
  <div class="lb-blockers">
    <div v-if="!items || items.length === 0" class="lb-blockers-empty">
      目前没有卡点
    </div>

    <div v-else class="lb-blockers-list">
      <div
        v-for="item in items"
        :key="item.id"
        class="lb-blocker-item"
      >
        <div class="lb-blocker-main">
          <div class="lb-blocker-title">
            {{ item.title }}
          </div>
          <div v-if="item.point_title" class="lb-blocker-point">
            知识点：{{ item.point_title }}
          </div>
          <div v-if="item.detail" class="lb-blocker-detail">
            {{ item.detail }}
          </div>
        </div>

        <div v-if="item.created_at" class="lb-blocker-date">
          {{ formatDate(item.created_at) }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.lb-blockers {
  width: 100%;
  color: var(--color-main-text);
  word-break: break-word;
  overflow-wrap: anywhere;
}

.lb-blockers-empty {
  padding: 20px 12px;
  text-align: center;
  font-size: 15px;
  color: var(--color-sub-text);
}

.lb-blockers-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.lb-blocker-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  background: var(--color-second);
  border: 1px solid var(--color-item-border);
}

.lb-blocker-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.lb-blocker-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-main-text);
  line-height: 1.4;
}

.lb-blocker-point {
  font-size: 13px;
  color: var(--color-sub-text);
}

.lb-blocker-detail {
  font-size: 13px;
  color: var(--color-sub-text);
  line-height: 1.4;
}

.lb-blocker-date {
  font-size: 13px;
  color: var(--color-sub-text);
  white-space: nowrap;
  flex-shrink: 0;
  margin-top: 2px;
}
</style>
