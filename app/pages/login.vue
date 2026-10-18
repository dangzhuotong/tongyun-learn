<script setup lang="ts">
// tongyun: 前端门禁登录页（只挡路人，不是安全鉴权）
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { tryGateLogin } from '@/tongyun/gate'

definePageMeta({ layout: 'empty' })
useSeoMeta({ title: '登录 · 橦云学习' })

const route = useRoute()
const router = useRouter()
const user = ref('')
const pass = ref('')
const error = ref('')

function submit() {
  if (!tryGateLogin(user.value, pass.value)) {
    error.value = '账号或密码不对'
    return
  }
  const next = typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : '/'
  router.replace(next === '/login' ? '/' : next)
}
</script>

<template>
  <section class="gate">
    <form class="card" data-testid="gate-form" @submit.prevent="submit">
      <h1>橦云学习</h1>
      <label>账号<input v-model="user" data-testid="gate-user" autocomplete="username" /></label>
      <label>密码<input v-model="pass" data-testid="gate-pass" type="password" autocomplete="current-password" /></label>
      <p v-if="error" class="err">{{ error }}</p>
      <button type="submit" data-testid="gate-submit">登录</button>
    </form>
  </section>
</template>

<style scoped>
.gate { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #fcf4e1; }
.card { width: 300px; padding: 28px; border-radius: 16px; background: #fff; display: flex; flex-direction: column; gap: 14px; box-shadow: 0 6px 24px rgba(0,0,0,.06); }
h1 { margin: 0 0 6px; font-size: 26px; text-align: center; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 14px; color: #555; }
input { padding: 10px 12px; border: 1px solid #ddd; border-radius: 10px; font-size: 16px; }
button { padding: 11px; border: 0; border-radius: 10px; background: #a4c48c; color: #fff; font-size: 16px; cursor: pointer; }
.err { margin: 0; color: #c0392b; font-size: 14px; }
</style>
