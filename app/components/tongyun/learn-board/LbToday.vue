<!-- tongyun: 学习看板组件（只读） -->
<script setup lang="ts">
import { computed } from 'vue'
import type { NextResp } from '@/tongyun/learn-board-api'
import { stateLabel, stateColor } from '@/tongyun/learn-board-api'
import { boardSubjectLabel, subjectSlot } from '@/tongyun/learn-board-glance'

interface Props {
  data: NextResp
  subjectTitles?: Record<string, string>
}

const props = withDefaults(defineProps<Props>(), {
  subjectTitles: () => ({}),
})

const hasItems = computed(() => {
  return (props.data?.recheck?.length ?? 0) > 0 || (props.data?.next?.length ?? 0) > 0
})

const subjectQuotas = computed(() => {
  const bySub = props.data?.new_point_quota?.by_subject_left || {}
  return Object.entries(bySub).map(([subId, left]) => {
    const known = props.subjectTitles[subId]
    const title = known || boardSubjectLabel({ id: subId, title: subId })
    return { id: subId, title, left }
  })
})

function subjectChip(subjectId?: string) {
  if (!subjectId) return ''
  const known = props.subjectTitles[subjectId]
  return known || boardSubjectLabel({ id: subjectId, title: subjectId })
}

function subjectChipClass(subjectId?: string) {
  const label = subjectChip(subjectId)
  if (label === 'Java') return 'is-java'
  if (label === '英语') return 'is-en'
  const slot = subjectSlot({
    id: subjectId,
    title: subjectId ? props.subjectTitles[subjectId] || '' : '',
  })
  if (slot === 'java') return 'is-java'
  if (slot === 'english') return 'is-en'
  return ''
}
</script>

<template>
  <div class="lb-today">
    <!-- 顶部名额行 -->
    <div class="lb-quota-bar">
      <span class="lb-quota-global">
        今天还能新开 <strong>{{ data?.new_point_quota?.global_left ?? 0 }}</strong> 个点
      </span>
      <div v-if="subjectQuotas.length > 0" class="lb-quota-subjects">
        <span v-for="sq in subjectQuotas" :key="sq.id" class="lb-quota-chip"> {{ sq.title }} 剩 {{ sq.left }} </span>
      </div>
    </div>

    <!-- 列表或空提示 -->
    <div v-if="!hasItems" class="lb-today-empty">今天没有要学的新点</div>

    <div v-else class="lb-today-list">
      <!-- 待复查条目 -->
      <div v-for="item in data.recheck || []" :key="'recheck-' + item.point_id" class="lb-today-item lb-recheck-item">
        <div class="lb-item-top">
          <span class="lb-badge lb-badge-recheck">待复查</span>
          <span class="lb-item-title">{{ item.title }}</span>
        </div>
      </div>

      <!-- 下一步条目 -->
      <div v-for="item in data.next || []" :key="'next-' + item.point_id" class="lb-today-item lb-next-item">
        <div class="lb-item-main">
          <div class="lb-item-title-row">
            <span
              v-if="subjectChip(item.subject_id)"
              class="lb-subject-chip"
              :class="subjectChipClass(item.subject_id)"
            >
              {{ subjectChip(item.subject_id) }}
            </span>
            <span class="lb-item-title font-bold">{{ item.title }}</span>
            <span class="lb-state-pill">
              <span class="lb-state-dot" :style="{ backgroundColor: stateColor(item.state) }" />
              <span class="lb-state-text">{{ stateLabel(item.state) }}</span>
            </span>
          </div>

          <div v-if="item.stage_title" class="lb-stage-title">
            {{ item.stage_title }}
          </div>

          <div v-if="item.reason" class="lb-item-reason">
            {{ item.reason }}
          </div>
        </div>

        <div class="lb-item-tag-box">
          <span v-if="item.opens_today" class="lb-badge lb-badge-opens-today"> 占今天新开名额 </span>
          <span v-else-if="item.opened_today" class="lb-badge lb-badge-opened-today"> 今天已开 </span>
          <span v-else class="lb-badge lb-badge-no-quota"> 不占名额 </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.lb-today {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
  color: var(--color-main-text);
  word-break: break-word;
  overflow-wrap: anywhere;
}

.lb-quota-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--color-second);
  border: 1px solid var(--color-item-border);
  border-radius: 8px;
  font-size: 14px;
}

.lb-quota-global {
  font-size: 14px;
  color: var(--color-main-text);

  strong {
    font-size: 16px;
    color: var(--color-select-bg);
  }
}

.lb-quota-subjects {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.lb-quota-chip {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 13px;
  background: var(--color-card-bg);
  border: 1px solid var(--color-item-border);
  color: var(--color-sub-text);
}

.lb-today-empty {
  padding: 24px 12px;
  text-align: center;
  font-size: 15px;
  color: var(--color-sub-text);
}

.lb-today-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.lb-today-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border-radius: 8px;
  background: var(--color-second);
  border: 1px solid var(--color-item-border);
}

.lb-item-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.lb-item-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.lb-item-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.lb-item-title {
  font-size: 15px;
  color: var(--color-main-text);

  &.font-bold {
    font-weight: 600;
  }
}

.lb-state-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--color-sub-text);
  flex-shrink: 0;
}

.lb-state-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.lb-stage-title {
  font-size: 13px;
  color: var(--color-sub-text);
}

.lb-item-reason {
  font-size: 13px;
  color: var(--color-sub-text);
  line-height: 1.4;
}

.lb-item-tag-box {
  display: flex;
  align-items: center;
  margin-top: 2px;
}

.lb-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.2;
}

.lb-badge-recheck {
  background: rgba(245, 158, 11, 0.15);
  color: #d97706;
  border: 1px solid rgba(245, 158, 11, 0.4);
  font-weight: 500;
}

.lb-badge-opens-today {
  background: rgba(59, 130, 246, 0.15);
  color: #2563eb;
  border: 1px solid rgba(59, 130, 246, 0.4);
}

.lb-badge-opened-today {
  background: rgba(20, 184, 166, 0.15);
  color: #0d9488;
  border: 1px solid rgba(20, 184, 166, 0.4);
}

.lb-badge-no-quota {
  background: var(--color-card-bg);
  color: var(--color-sub-text);
  border: 1px solid var(--color-item-border);
}

.lb-subject-chip {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  background: var(--color-card-bg);
  border: 1px solid var(--color-item-border);
  color: var(--color-main-text);
  flex-shrink: 0;

  &.is-java {
    background: rgba(59, 130, 246, 0.15);
    border-color: rgba(59, 130, 246, 0.45);
    color: #2563eb;
  }

  &.is-en {
    background: rgba(20, 184, 166, 0.15);
    border-color: rgba(20, 184, 166, 0.45);
    color: #0d9488;
  }
}
</style>
