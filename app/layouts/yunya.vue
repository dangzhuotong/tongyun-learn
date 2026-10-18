<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { withAppBaseURL } from '@/core/utils/base-url'
import { getActiveSubject, setActiveSubject, type ActiveSubject } from '@/tongyun/subject'

const mark = withAppBaseURL('/yunya-mark.svg')
const router = useRouter()
const currentSubject = ref<ActiveSubject>('english')

function syncSubject() {
  currentSubject.value = getActiveSubject()
}

function selectSubject(s: ActiveSubject) {
  currentSubject.value = s
  setActiveSubject(s)
}

onMounted(() => {
  document.documentElement.classList.add('yunya-on')
  syncSubject()
  window.addEventListener('tongyun-subject-changed', syncSubject)
})

onUnmounted(() => {
  document.documentElement.classList.remove('yunya-on')
  window.removeEventListener('tongyun-subject-changed', syncSubject)
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
        <!-- tongyun: 学科切换 -->
        <div class="yy-subject-switcher">
          <NuxtLink
            to="/practice?subject=english"
            class="yy-subject"
            :class="{ active: currentSubject === 'english' }"
            @click="selectSubject('english')"
          >
            英语
          </NuxtLink>
          <NuxtLink
            to="/practice?subject=java"
            class="yy-subject"
            :class="{ active: currentSubject === 'java' }"
            @click="selectSubject('java')"
          >
            Java
          </NuxtLink>
          <NuxtLink
            to="/practice?subject=ai"
            class="yy-subject"
            :class="{ active: currentSubject === 'ai' }"
            @click="selectSubject('ai')"
          >
            AI
          </NuxtLink>
        </div>
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
