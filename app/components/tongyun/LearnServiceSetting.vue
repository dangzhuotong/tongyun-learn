<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { BaseButton, BaseInput, Toast } from '@/base'
import SettingItem from '@/components/setting/SettingItem.vue'
import { getLearnConfig, saveLearnConfig, clearLearnConfig, learnCheckAuth } from '@/tongyun/learn-client'

const router = useRouter()

const url = ref('/learn/api/')
const token = ref('')
const testing = ref(false)

onMounted(() => {
  const cfg = getLearnConfig()
  url.value = cfg.url || '/learn/api/'
  token.value = cfg.token || ''
})

function onSave() {
  saveLearnConfig({ url: url.value, token: token.value })
  Toast.success('已保存')
}

async function onTest() {
  testing.value = true
  try {
    const { result } = await learnCheckAuth({ url: url.value, token: token.value })
    if (result === 'ok') {
      Toast.success('连接正常')
    } else if (result === 'bad_token') {
      Toast.error('令牌不对')
    } else {
      Toast.error('连不上服务')
    }
  } catch {
    Toast.error('连不上服务')
  } finally {
    testing.value = false
  }
}

function onClear() {
  clearLearnConfig()
  url.value = '/learn/api/'
  token.value = ''
  Toast.success('已清除')
}
</script>

<template>
  <div class="learn-service-setting">
    <SettingItem
      title="学习服务（AI 讲解）"
      desc="tongyun-learn 服务地址和令牌，只存在本浏览器 localStorage。默认同域 /learn/api/"
    />
    <div class="flex flex-col gap-3 max-w-xl my-2">
      <div class="flex items-center gap-3">
        <span class="w-20 shrink-0 text-sm opacity-80">服务地址</span>
        <BaseInput class="flex-1" v-model="url" placeholder="/learn/api/" clearable />
      </div>
      <div class="flex items-center gap-3">
        <span class="w-20 shrink-0 text-sm opacity-80">令牌</span>
        <BaseInput class="flex-1" v-model="token" type="password" placeholder="web 令牌" clearable />
      </div>
      <div class="flex items-center justify-between gap-3 mt-1">
        <div class="flex flex-col gap-1">
          <button
            type="button"
            class="text-sm text-[var(--color-link)] hover:underline cursor-pointer bg-transparent border-none p-0 inline-flex items-center min-h-[44px]"
            @click="router.push('/')"
          >
            打开云芽英语
          </button>
        </div>
        <div class="flex gap-3 justify-end">
          <BaseButton type="info" @click="onClear">清除</BaseButton>
          <BaseButton type="info" :loading="testing" @click="onTest">测试连接</BaseButton>
          <BaseButton type="primary" @click="onSave">保存</BaseButton>
        </div>
      </div>
    </div>
    <div class="line my-4"></div>
  </div>
</template>

<style scoped lang="scss">
.line {
  border-bottom: 1px solid var(--color-border, rgba(125, 125, 125, 0.2));
}
</style>
