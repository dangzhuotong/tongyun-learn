<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

// tongyun: 旧的 /typewords 词书入口改去云芽练习。静态页用 meta refresh，进站后再 replace。
definePageMeta({
  layout: false,
})

const router = useRouter()
const baseURL = useRuntimeConfig().app.baseURL || '/'
const target = `${baseURL.endsWith('/') ? baseURL : `${baseURL}/`}practice`

useHead({
  title: '云芽英语',
  meta: [{ 'http-equiv': 'refresh', content: `0; url=${target}` }],
})

onMounted(() => {
  router.replace('/practice')
})
</script>

<template>
  <p class="jump">正在进入练习…</p>
</template>

<style scoped>
.jump {
  margin: 48px auto;
  max-width: 24rem;
  font-family: 'PingFang SC', 'Noto Sans SC', sans-serif;
  color: #4d7c5d;
}
</style>
