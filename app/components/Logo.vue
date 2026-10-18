<script setup lang="ts">
import { useSettingStore } from '@/core/stores/setting.ts'
import { useRouter } from 'vue-router'
import { withAppBaseURL } from '@/core/utils/base-url'

const settingStore = useSettingStore()
const router = useRouter()
const darkLogoSrc = withAppBaseURL('/imgs/logo/logo-text-black.png')
const lightLogoSrc = withAppBaseURL('/imgs/logo/logo-text-white.png')

function goHome() {
  // tongyun: 站点入口是今日
  router.push('/')
}
</script>

<template>
  <div class="center" @click="goHome">
    <img v-show="settingStore.theme === 'dark'" :src="lightLogoSrc" alt="" />
    <img v-show="settingStore.theme !== 'dark'" :src="darkLogoSrc" alt="" />
  </div>
</template>

<style scoped lang="scss">
img {
  cursor: pointer;
  height: 2rem;
}
</style>
