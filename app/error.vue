<script setup lang="ts">
import type { NuxtError } from '#app'

const props = defineProps({
  error: Object as () => NuxtError,
})
</script>

<template>
  <div class="h-screen center flex-col">
    <h1>{{ error?.statusCode }}</h1>
    <h2>{{ error?.message }}</h2>
    <NuxtLink to="/learn-board">返回学习看板</NuxtLink>
  </div>
</template>
