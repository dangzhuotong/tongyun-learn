<!-- tongyun: 学习看板组件（只读） -->
<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import type { Subject, SubjectMap, MapStage, MapPoint } from '@/tongyun/learn-board-api'
import { fetchMap, POINT_STATES, stateLabel, stateColor } from '@/tongyun/learn-board-api'
import { resolveBoardSubjects } from '@/tongyun/learn-board-glance'

interface Props {
  subjects: Subject[]
}

const props = defineProps<Props>()
const router = useRouter()

const selectedSubjectId = ref('')
const mapCache = ref<Record<string, SubjectMap>>({})
const mapState = ref<'loading' | 'ok' | 'bad_token' | 'unreachable'>('loading')
const openStages = ref<Record<string, boolean>>({})
const expandedPointId = ref<string | null>(null)

const currentMap = computed<SubjectMap | null>(() => {
  if (!selectedSubjectId.value) return null
  return mapCache.value[selectedSubjectId.value] || null
})

const sortedStages = computed<MapStage[]>(() => {
  if (!currentMap.value?.stages) return []
  return currentMap.value.stages.slice().sort((a, b) => a.ord - b.ord)
})

const pointLookup = computed(() => {
  const map = new Map<string, MapPoint>()
  if (!currentMap.value?.stages) return map
  for (const st of currentMap.value.stages) {
    for (const pt of st.points || []) {
      map.set(pt.id, pt)
    }
  }
  return map
})

function initDefaultStages(map: SubjectMap) {
  const stages = map.stages?.slice().sort((a, b) => a.ord - b.ord) || []
  const newOpen: Record<string, boolean> = {}
  let firstUnpassedFound = false
  for (const st of stages) {
    if (!st.passed && !firstUnpassedFound) {
      newOpen[st.id] = true
      firstUnpassedFound = true
    } else {
      newOpen[st.id] = false
    }
  }
  if (!firstUnpassedFound && stages.length > 0) {
    newOpen[stages[0].id] = true
  }
  openStages.value = newOpen
  expandedPointId.value = null
}

async function loadMap(subjectId: string, force = false) {
  if (!subjectId) return
  if (!force && mapCache.value[subjectId]) {
    mapState.value = 'ok'
    initDefaultStages(mapCache.value[subjectId])
    return
  }

  mapState.value = 'loading'
  const res = await fetchMap(subjectId)
  if (res.ok) mapCache.value[subjectId] = res.data
  // 切学科后旧请求才回来：只缓存，不改当前显示状态
  if (selectedSubjectId.value !== subjectId) return
  if (res.ok) {
    mapState.value = 'ok'
    initDefaultStages(res.data)
  } else if (res.kind === 'bad_token') {
    mapState.value = 'bad_token'
  } else {
    mapState.value = 'unreachable'
  }
}

function selectSubject(id: string) {
  if (selectedSubjectId.value === id) return
  selectedSubjectId.value = id
  loadMap(id)
}

function toggleStage(stageId: string) {
  openStages.value[stageId] = !openStages.value[stageId]
}

function togglePoint(pointId: string) {
  if (expandedPointId.value === pointId) {
    expandedPointId.value = null
  } else {
    expandedPointId.value = pointId
  }
}

function getStageStateCounts(stage: MapStage) {
  const counts: Record<string, number> = {}
  for (const p of stage.points || []) {
    const st = p.stats?.state || 'locked'
    counts[st] = (counts[st] || 0) + 1
  }
  return POINT_STATES.map(s => ({ key: s.key, color: s.color, count: counts[s.key] || 0 })).filter(s => s.count > 0)
}

function goToSetting() {
  router.push('/setting?index=0')
}

function preferredSubjectId(subs: Subject[]): string {
  if (!subs?.length) return ''
  return resolveBoardSubjects(subs).java?.id || subs[0].id
}

function reload() {
  mapCache.value = {}
  expandedPointId.value = null
  if (selectedSubjectId.value) {
    loadMap(selectedSubjectId.value, true)
  }
}

defineExpose({ reload })

watch(
  () => props.subjects,
  subs => {
    if (subs && subs.length > 0) {
      if (!selectedSubjectId.value || !subs.some(s => s.id === selectedSubjectId.value)) {
        const id = preferredSubjectId(subs)
        selectedSubjectId.value = id
        loadMap(id)
      }
    }
  },
  { immediate: true }
)

onMounted(() => {
  if (props.subjects.length > 0 && !selectedSubjectId.value) {
    const id = preferredSubjectId(props.subjects)
    selectedSubjectId.value = id
    loadMap(id)
  }
})
</script>

<template>
  <div class="lb-map">
    <!-- 学科切换按钮排 -->
    <div v-if="subjects && subjects.length > 0" class="lb-map-tabs">
      <button
        v-for="sub in subjects"
        :key="sub.id"
        type="button"
        class="lb-map-tab-btn"
        :class="{ active: sub.id === selectedSubjectId }"
        @click="selectSubject(sub.id)"
      >
        {{ sub.title }}
      </button>
    </div>

    <!-- 地图加载/错误/内容 -->
    <div class="lb-map-content">
      <div v-if="mapState === 'loading'" class="lb-state-box">
        <span>加载中…</span>
      </div>

      <div v-else-if="mapState === 'bad_token'" class="lb-state-box">
        <p class="lb-state-text">暂不可用</p>
      </div>

      <div v-else-if="mapState === 'unreachable'" class="lb-state-box">
        <p class="lb-state-text">暂不可用</p>
      </div>

      <div v-else-if="mapState === 'ok' && sortedStages.length === 0" class="lb-map-empty">暂无阶段数据</div>

      <div v-else-if="mapState === 'ok'" class="lb-stages-list">
        <div v-for="stage in sortedStages" :key="stage.id" class="lb-stage-card">
          <!-- 阶段折叠头（整行可点，>=44px 高） -->
          <button type="button" class="lb-stage-header" @click="toggleStage(stage.id)">
            <div class="lb-stage-header-left">
              <span class="lb-stage-arrow" :class="{ 'is-open': openStages[stage.id] }"> ▸ </span>
              <span class="lb-stage-title"> 第 {{ stage.ord }} 阶段 · {{ stage.title }} </span>
              <span v-if="stage.passed" class="lb-stage-passed-badge"> 已通过 </span>
            </div>

            <!-- 该阶段各状态计数小圆点 -->
            <div class="lb-stage-header-right">
              <span v-for="item in getStageStateCounts(stage)" :key="item.key" class="lb-stage-stat-pill">
                <span class="lb-stat-dot" :style="{ backgroundColor: item.color }" />
                <span class="lb-stat-count">{{ item.count }}</span>
              </span>
            </div>
          </button>

          <!-- 阶段展开后的点列表 -->
          <div v-if="openStages[stage.id]" class="lb-stage-points">
            <div v-if="!stage.points || stage.points.length === 0" class="lb-points-empty">该阶段暂无知识点</div>

            <div v-for="point in stage.points" :key="point.id" class="lb-point-group">
              <!-- 知识点行（按钮，>=44px 高） -->
              <button
                type="button"
                class="lb-point-row"
                :class="{ 'is-expanded': expandedPointId === point.id }"
                @click="togglePoint(point.id)"
              >
                <div class="lb-point-left">
                  <span class="lb-point-dot" :style="{ backgroundColor: stateColor(point.stats?.state) }" />
                  <span class="lb-point-title">{{ point.title }}</span>
                </div>
                <div class="lb-point-right">
                  <span class="lb-point-state-text" :style="{ color: stateColor(point.stats?.state) }">
                    {{ stateLabel(point.stats?.state) }}
                  </span>
                  <span class="lb-expand-indicator">
                    {{ expandedPointId === point.id ? '收起' : '前置' }}
                  </span>
                </div>
              </button>

              <!-- 点击展开的前置详情 -->
              <div v-if="expandedPointId === point.id" class="lb-prereqs-box">
                <div v-if="!point.prereqs || point.prereqs.length === 0" class="lb-prereq-empty">没有前置</div>

                <div v-else class="lb-prereq-list">
                  <div v-for="pr in point.prereqs" :key="pr.id" class="lb-prereq-row">
                    <div class="lb-prereq-left">
                      <span class="lb-prereq-kind-badge" :class="pr.kind === 'hard' ? 'kind-hard' : 'kind-soft'">
                        {{ pr.kind === 'hard' ? '硬前置' : '软前置' }}
                      </span>
                      <span class="lb-prereq-title">
                        {{ pointLookup.get(pr.id)?.title || pr.id }}
                      </span>
                    </div>

                    <div class="lb-prereq-right">
                      <span
                        class="lb-prereq-state-dot"
                        :style="{ backgroundColor: stateColor(pointLookup.get(pr.id)?.stats?.state) }"
                      />
                      <span
                        class="lb-prereq-state-text"
                        :style="{ color: stateColor(pointLookup.get(pr.id)?.stats?.state) }"
                      >
                        {{ stateLabel(pointLookup.get(pr.id)?.stats?.state) }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.lb-map {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
  color: var(--color-main-text);
  word-break: break-word;
  overflow-wrap: anywhere;
}

.lb-map-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.lb-map-tab-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  padding: 0 16px;
  border-radius: 8px;
  font-size: 15px;
  background: var(--color-second);
  border: 1px solid var(--color-item-border);
  color: var(--color-main-text);
  cursor: pointer;
  touch-action: manipulation;
  transition: all 0.2s;

  &:hover {
    background: var(--color-fourth);
  }

  &.active {
    background: var(--color-select-bg);
    border-color: var(--color-select-bg);
    color: white;
    font-weight: 600;
  }
}

.lb-map-content {
  width: 100%;
}

.lb-state-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px 12px;
  text-align: center;
  gap: 12px;
}

.lb-state-text {
  margin: 0;
  font-size: 15px;
  color: var(--color-sub-text);
}

.lb-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  padding: 0 18px;
  font-size: 15px;
  border-radius: 8px;
  border: 1px solid var(--color-item-border);
  background: var(--color-second);
  color: var(--color-main-text);
  cursor: pointer;
  touch-action: manipulation;
}

.lb-map-empty {
  padding: 20px 12px;
  text-align: center;
  font-size: 15px;
  color: var(--color-sub-text);
}

.lb-stages-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.lb-stage-card {
  border-radius: 8px;
  background: var(--color-second);
  border: 1px solid var(--color-item-border);
  overflow: hidden;
}

.lb-stage-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 44px;
  padding: 10px 12px;
  background: transparent;
  border: none;
  cursor: pointer;
  touch-action: manipulation;
  color: var(--color-main-text);
  text-align: left;
  gap: 8px;
  transition: background 0.2s;

  &:hover {
    background: var(--color-fourth);
  }
}

.lb-stage-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex: 1;
}

.lb-stage-arrow {
  display: inline-block;
  font-size: 14px;
  color: var(--color-sub-text);
  transition: transform 0.2s ease;

  &.is-open {
    transform: rotate(90deg);
  }
}

.lb-stage-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-main-text);
}

.lb-stage-passed-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 7px;
  border-radius: 6px;
  font-size: 12px;
  background: rgba(34, 197, 94, 0.15);
  color: #16a34a;
  border: 1px solid rgba(34, 197, 94, 0.4);
}

.lb-stage-header-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.lb-stage-stat-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--color-sub-text);
}

.lb-stat-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.lb-stat-count {
  line-height: 1;
}

.lb-stage-points {
  display: flex;
  flex-direction: column;
  padding: 6px 10px 10px 10px;
  gap: 6px;
  border-top: 1px solid var(--color-item-border);
}

.lb-points-empty {
  padding: 12px;
  text-align: center;
  font-size: 14px;
  color: var(--color-sub-text);
}

.lb-point-group {
  display: flex;
  flex-direction: column;
}

.lb-point-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 44px;
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--color-card-bg);
  border: 1px solid var(--color-item-border);
  color: var(--color-main-text);
  cursor: pointer;
  touch-action: manipulation;
  text-align: left;
  gap: 8px;
  transition: background 0.2s;

  &:hover {
    background: var(--color-second);
  }

  &.is-expanded {
    border-bottom-left-radius: 0;
    border-bottom-right-radius: 0;
    border-bottom-color: transparent;
    background: var(--color-second);
  }
}

.lb-point-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.lb-point-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.lb-point-title {
  font-size: 15px;
  color: var(--color-main-text);
}

.lb-point-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.lb-point-state-text {
  font-size: 13px;
  font-weight: 500;
}

.lb-expand-indicator {
  font-size: 12px;
  color: var(--color-sub-text);
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--color-second);
}

.lb-prereqs-box {
  padding: 10px 12px;
  background: var(--color-second);
  border: 1px solid var(--color-item-border);
  border-top: none;
  border-bottom-left-radius: 6px;
  border-bottom-right-radius: 6px;
}

.lb-prereq-empty {
  font-size: 13px;
  color: var(--color-sub-text);
  padding: 4px 0;
}

.lb-prereq-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.lb-prereq-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 0;
  font-size: 14px;
}

.lb-prereq-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.lb-prereq-kind-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.2;
  flex-shrink: 0;

  &.kind-hard {
    background: var(--color-main-text);
    color: var(--color-card-bg);
    font-weight: 600;
  }

  &.kind-soft {
    background: transparent;
    border: 1px solid var(--color-sub-text);
    color: var(--color-sub-text);
  }
}

.lb-prereq-title {
  color: var(--color-main-text);
}

.lb-prereq-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.lb-prereq-state-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.lb-prereq-state-text {
  font-size: 13px;
}
</style>
