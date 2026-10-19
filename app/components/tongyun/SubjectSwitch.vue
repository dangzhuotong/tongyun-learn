<script setup lang="ts">
import { useActiveSubject } from '@/tongyun/subject/active-subject'

const { activeId, subjects, setActiveSubject } = useActiveSubject()

function onChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  setActiveSubject(value)
}
</script>

<template>
  <label class="subject-switch">
    <span class="sr-only">学科</span>
    <select
      :value="activeId"
      data-testid="subject-switch"
      aria-label="学科"
      @change="onChange"
    >
      <option v-for="s in subjects" :key="s.id" :value="s.id">
        {{ s.title }}
      </option>
    </select>
  </label>
</template>

<style scoped lang="scss">
.subject-switch select {
  appearance: none;
  border: 1px solid transparent;
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: 600;
  padding: 2px 4px;
  border-radius: 6px;
}

.subject-switch select:hover {
  border-color: currentColor;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
