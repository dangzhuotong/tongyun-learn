<!-- tongyun: 学习看板组件（只读） -->
<script setup lang="ts">
import type { Subject } from '@/tongyun/learn-board-api'
import { POINT_STATES, formatRetention } from '@/tongyun/learn-board-api'

interface Props {
  subjects: Subject[]
  retention: Record<string, number | null | undefined>
  retentionLoaded: Record<string, boolean>
}

const props = defineProps<Props>()

function getTotalPoints(sub: Subject): number {
  if (!sub.points_by_state) return 0
  return Object.values(sub.points_by_state).reduce((sum, val) => sum + (Number(val) || 0), 0)
}

function getMasteredPoints(sub: Subject): number {
  return sub.points_by_state?.['mastered'] || 0
}

function getSegments(sub: Subject) {
  const total = getTotalPoints(sub)
  return POINT_STATES.map(s => {
    const count = sub.points_by_state?.[s.key] || 0
    const pct = total > 0 ? (count / total) * 100 : 0
    return {
      key: s.key,
      label: s.label,
      color: s.color,
      count,
      pct,
    }
  })
}

function getRetentionText(subId: string): string {
  if (!props.retentionLoaded[subId]) {
    return '—'
  }
  return formatRetention(props.retention[subId])
}
</script>

<template>
  <div class="lb-subjects">
    <div v-if="!subjects || subjects.length === 0" class="lb-subjects-empty">
      暂无学科数据
    </div>

    <div v-else class="lb-subjects-grid">
      <div
        v-for="sub in subjects"
        :key="sub.id"
        class="lb-subject-card"
      >
        <!-- 标题行与掌握进度 -->
        <div class="lb-subject-top">
          <h3 class="lb-subject-title">{{ sub.title }}</h3>
          <span class="lb-subject-stat">
            掌握 {{ getMasteredPoints(sub) }} / 共 {{ getTotalPoints(sub) }}
          </span>
        </div>

        <!-- 堆叠进度条 -->
        <div class="lb-progress-bar">
          <template v-if="getTotalPoints(sub) > 0">
            <div
              v-for="seg in getSegments(sub)"
              :key="seg.key"
              class="lb-progress-segment"
              :style="{
                width: `${seg.pct}%`,
                backgroundColor: seg.color,
              }"
              :title="`${seg.label}: ${seg.count}`"
            />
          </template>
          <div v-else class="lb-progress-empty" />
        </div>

        <!-- 状态 chips -->
        <div class="lb-chips-row">
          <span
            v-for="seg in getSegments(sub)"
            :key="seg.key"
            class="lb-chip"
            :class="{ 'is-zero': seg.count === 0 }"
          >
            <span
              class="lb-chip-dot"
              :style="{ backgroundColor: seg.color }"
            />
            <span class="lb-chip-text">{{ seg.label }} {{ seg.count }}</span>
          </span>
        </div>

        <!-- 保持率 -->
        <div class="lb-retention-row">
          <span class="lb-retention-label">30 天保持率</span>
          <span class="lb-retention-val">{{ getRetentionText(sub.id) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.lb-subjects {
  width: 100%;
  color: var(--color-main-text);
  word-break: break-word;
  overflow-wrap: anywhere;
}

.lb-subjects-empty {
  padding: 20px 12px;
  text-align: center;
  font-size: 15px;
  color: var(--color-sub-text);
}

.lb-subjects-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.lb-subject-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border-radius: 8px;
  background: var(--color-second);
  border: 1px solid var(--color-item-border);
}

.lb-subject-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.lb-subject-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-main-text);
}

.lb-subject-stat {
  font-size: 14px;
  color: var(--color-sub-text);
}

.lb-progress-bar {
  display: flex;
  width: 100%;
  height: 8px;
  border-radius: 4px;
  overflow: hidden;
  background: var(--color-third);
}

.lb-progress-segment {
  height: 100%;
  transition: width 0.3s ease;
}

.lb-progress-empty {
  width: 100%;
  height: 100%;
  background: var(--color-third);
}

.lb-chips-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.lb-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 7px;
  border-radius: 6px;
  font-size: 13px;
  background: var(--color-card-bg);
  border: 1px solid var(--color-item-border);
  color: var(--color-main-text);

  &.is-zero {
    opacity: 0.45;
    color: var(--color-sub-text);
  }
}

.lb-chip-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.lb-retention-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 4px;
  border-top: 1px dashed var(--color-line);
  font-size: 13px;
}

.lb-retention-label {
  color: var(--color-sub-text);
}

.lb-retention-val {
  font-weight: 600;
  color: var(--color-main-text);
}
</style>
