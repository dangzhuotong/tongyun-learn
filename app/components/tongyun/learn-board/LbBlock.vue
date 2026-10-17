<!-- tongyun: 学习看板组件（只读） -->
<script setup lang="ts">
import { useRouter } from 'vue-router'

interface Props {
  title: string
  state: 'loading' | 'ok' | 'bad_token' | 'unreachable' | 'soon'
  soonText?: string
  prominent?: boolean
  accent?: 'java' | ''
}

const props = withDefaults(defineProps<Props>(), {
  soonText: '',
  prominent: false,
  accent: '',
})

const router = useRouter()

function goToSetting() {
  router.push('/setting?index=0')
}
</script>

<template>
  <section
    class="lb-block"
    :class="{
      'is-prominent': props.prominent,
      'is-java': props.accent === 'java',
    }"
  >
    <header class="lb-block-header">
      <h2 class="lb-block-title">{{ title }}</h2>
      <div v-if="$slots.extra" class="lb-block-extra">
        <slot name="extra" />
      </div>
    </header>

    <div class="lb-block-body">
      <div v-if="state === 'loading'" class="lb-state-box lb-state-loading">
        <span>加载中…</span>
      </div>

      <div v-else-if="state === 'bad_token'" class="lb-state-box lb-state-bad-token">
        <p class="lb-state-text">令牌不对，去设置改</p>
        <button type="button" class="lb-action-btn" @click="goToSetting">去设置</button>
      </div>

      <div v-else-if="state === 'unreachable'" class="lb-state-box lb-state-unreachable">
        <p class="lb-state-text">连不上学习服务</p>
      </div>

      <div v-else-if="state === 'soon'" class="lb-state-box lb-state-soon">
        <p class="lb-soon-text">{{ soonText || '即将接入' }}</p>
      </div>

      <div v-else-if="state === 'ok'" class="lb-content">
        <slot />
      </div>
    </div>
  </section>
</template>

<style scoped lang="scss">
.lb-block {
  background: var(--color-card-bg);
  border: 1px solid var(--color-item-border);
  border-radius: 12px;
  padding: 16px;
  box-sizing: border-box;
  width: 100%;
  color: var(--color-main-text);
  word-break: break-word;
  overflow-wrap: anywhere;
}

.lb-block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  min-height: 28px;
}

.lb-block-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-main-text);
  line-height: 1.4;
}

.lb-block.is-prominent .lb-block-title {
  font-size: 18px;
}

.lb-block.is-java {
  border-color: var(--color-select-bg);
  box-shadow: 0 0 0 1px var(--color-select-bg);
}

.lb-block-extra {
  display: flex;
  align-items: center;
  gap: 8px;
}

.lb-block-body {
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

.lb-soon-text {
  margin: 0;
  font-size: 14px;
  color: var(--color-sub-text);
}

.lb-state-loading {
  font-size: 14px;
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
  transition:
    opacity 0.2s,
    background 0.2s;

  &:hover {
    background: var(--color-fourth);
  }

  &:active {
    opacity: 0.8;
  }
}

.lb-content {
  width: 100%;
}
</style>
