<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { withAppBaseURL } from '@/core/utils/base-url'

const mark = withAppBaseURL('/yunya-mark.svg')

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
      <NuxtLink to="/" class="yy-brand">
        <img :src="mark" alt="" />
        <span>云芽英语</span>
      </NuxtLink>
      <nav class="yy-nav" aria-label="云芽英语">
        <NuxtLink to="/">今日</NuxtLink>
        <NuxtLink to="/practice">练习</NuxtLink>
        <NuxtLink to="/coach">教练</NuxtLink>
        <NuxtLink to="/settings">设置</NuxtLink>
      </nav>
    </header>
    <main class="yy-main">
      <slot />
    </main>
    <nav class="yy-tab" aria-label="云芽英语">
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
