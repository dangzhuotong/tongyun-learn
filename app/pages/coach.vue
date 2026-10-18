<script setup lang="ts">
// tongyun: 教练页暂不接后端，只给本地练习入口
import { useRouter } from 'vue-router'

definePageMeta({
  layout: 'yunya',
})

useSeoMeta({
  title: '橦云学习',
})

const router = useRouter()
</script>

<template>
  <section class="coach">
    <p class="eyebrow">橦云学习</p>
    <h1>教练</h1>
    <div class="yy-card panel">
      <p>薄弱点分析和每周计划还在做。先去练习，把今天的词敲一轮。</p>
      <button type="button" class="yy-btn" data-testid="go-practice" @click="router.push('/practice')">去练习</button>
    </div>
  </section>
</template>
<style scoped lang="scss">
.coach {
  padding-top: 28px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.eyebrow {
  margin: 0;
  color: var(--yy-matcha);
  letter-spacing: 0.14em;
  font-size: 13px;
}

h1 {
  margin: 8px 0 0;
  font-size: 40px;
  font-weight: 650;
}

h2 {
  margin: 0;
  font-size: 16px;
  color: var(--yy-ink-soft);
  font-weight: 600;
}

.sub,
.empty,
.summary,
.list p,
.plan p {
  margin: 0;
  line-height: 1.6;
  color: var(--yy-ink-soft);
}

.summary {
  color: var(--yy-ink);
  font-size: 20px;
}

.panel {
  padding: 22px 24px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
}

.skeleton {
  min-height: 140px;
}

.actions {
  display: flex;
  gap: 10px;
}

.list,
.plan {
  margin: 0;
  padding: 0;
  width: 100%;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.plan {
  list-style: decimal;
  padding-left: 1.2rem;
}

.row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.row strong,
.plan strong {
  font-size: 18px;
  color: var(--yy-ink);
}

.tag,
.count {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--yy-matcha-soft);
  color: var(--yy-matcha-deep);
}

.count {
  background: var(--yy-bg-deep);
  color: var(--yy-ink-soft);
}
</style>
