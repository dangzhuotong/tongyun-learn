<script setup lang="ts">
import { computed } from 'vue'
import { SELF_LABELS, SELF_OPTIONS } from '@/tongyun/subject/self-assessment'
import type { Card, SelfAssessment } from '@/tongyun/subject/types'

const props = defineProps<{
  card: Pick<Card, 'type' | 'rubric'>
  modelValue?: SelfAssessment | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: SelfAssessment): void
}>()

const rubric = computed(() => props.card.rubric ?? [])
const heading = computed(() => (props.card.type === 'project' ? '项目自评' : '口述自评'))

function choose(value: SelfAssessment) {
  emit('update:modelValue', value)
}
</script>

<template>
  <section class="self-grade" data-testid="self-grade">
    <p class="heading">{{ heading }}</p>
    <p class="hint">对照下面的评分要点，给自己评一档。不会 1 天后再来，半会 3 天，会走正常间隔。</p>
    <ul class="rubric" data-testid="self-rubric">
      <li v-for="(item, i) in rubric" :key="i">{{ item }}</li>
    </ul>
    <div class="choices" role="group" aria-label="自评">
      <button
        v-for="option in SELF_OPTIONS"
        :key="option"
        type="button"
        class="yy-btn self-btn"
        :class="[`is-${option}`, { on: modelValue === option }]"
        :data-testid="`self-${option}`"
        :aria-pressed="modelValue === option"
        @click="choose(option)"
      >
        {{ SELF_LABELS[option] }}
      </button>
    </div>
  </section>
</template>

<style scoped lang="scss">
.self-grade {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.heading {
  margin: 0;
  font-weight: 650;
}

.hint {
  margin: 0;
  color: var(--yy-ink-soft);
  font-size: 13px;
  line-height: 1.6;
}

.rubric {
  margin: 0;
  padding-left: 20px;
  line-height: 1.8;
}

.choices {
  display: flex;
  gap: 10px;
}

.self-btn.on {
  outline: 2px solid var(--yy-matcha-deep, #6b8f4e);
}
</style>
