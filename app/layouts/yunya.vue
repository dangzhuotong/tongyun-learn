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
      <div class="yy-brand-block">
        <NuxtLink to="/" class="yy-brand">
          <img :src="mark" alt="" />
          <span>橦云学习</span>
        </NuxtLink>
        <!-- tongyun: 学科先占位，只显示英语 -->
        <span class="yy-subject">英语</span>
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
