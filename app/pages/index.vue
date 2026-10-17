<script setup lang="ts">
// tongyun: 打开站点（/ ，部署在 /words/ 下就是 /words/）直接进学习看板
import LearnBoard from './learn-board.vue'

definePageMeta({
  layout: 'default',
})
</script>

<template>
  <LearnBoard />
</template>
