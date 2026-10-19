<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { withAppBaseURL } from '@/core/utils/base-url'
// tongyun: layout 只引 active-subject，题库由 bank.ts 按需动态 import
import { useActiveSubject } from '@/tongyun/subject/active-subject'

const mark = withAppBaseURL('/yunya-mark.svg')
const { active } = useActiveSubject()

onMounted(() => {
  document.documentElement.classList.add('yunya-on')
})

onUnmounted(() => {
  document.documentElement.classList.remove('yunya-on')
})
</script>

<template>
  <div class="yunya">
    <header class="yy-top">
      <div class="yy-brand-block" :data-subject="active.id">
        <NuxtLink to="/" class="yy-brand">
          <img :src="mark" alt="" />
          <span>橦云学习</span>
        </NuxtLink>
        <!-- tongyun: 学科切换，由注册表驱动；layout 只引 active-subject -->
        <SubjectSwitch class="yy-subject" />
      </div>
      <nav class="yy-nav" aria-label="橦云学习">
        <NuxtLink to="/">今日</NuxtLink>
        <NuxtLink to="/practice">练习</NuxtLink>
        <NuxtLink to="/coach">教练</NuxtLink>
        <NuxtLink to="/settings">设置</NuxtLink>
      </nav>
    </header>
    <main class="yy-main">
      <slot />
    </main>
    <nav class="yy-tab" aria-label="橦云学习">
      <NuxtLink to="/">今日</NuxtLink>
      <NuxtLink to="/practice">练习</NuxtLink>
      <NuxtLink to="/coach">教练</NuxtLink>
      <NuxtLink to="/settings">设置</NuxtLink>
    </nav>
  </div>
</template>

<style lang="scss">
@use '../assets/css/yunya.scss';
</style>
