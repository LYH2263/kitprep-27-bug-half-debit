<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, errText } from '../api'

const leaf = ref<any[]>([])
const semi = ref<any[]>([])
const kind = ref<'leaf' | 'semi'>('leaf')
const code = ref('')
const qty = ref(1)
const msg = ref('')
const error = ref('')

const options = computed(() => (kind.value === 'leaf' ? leaf.value : semi.value))

async function reload() {
  leaf.value = await api('/inventory')
  semi.value = await api('/inventory/semi')
  if (!options.value.some((r: any) => r.code === code.value)) {
    code.value = options.value[0]?.code ?? ''
  }
}

async function adjust() {
  msg.value = ''
  error.value = ''
  try {
    const r = await api('/inventory/adjust', {
      method: 'POST',
      body: JSON.stringify({ kind: kind.value, code: code.value, qty: Number(qty.value) }),
    })
    msg.value = `已加账：${r.name} 账面 ${r.stock_qty}`
    await reload()
  } catch (e) {
    error.value = errText(e)
  }
}

onMounted(reload)
</script>

<template>
  <h1>库存</h1>
  <p class="sub">叶料仓 / 半成品仓两本账分立 · 备料占用单列 · 结存只加账面</p>

  <div class="card">
    <h2 style="margin-top:0">入库（只加账面）</h2>
    <div class="kp-adjust-form">
      <select v-model="kind">
        <option value="leaf">叶料仓</option>
        <option value="semi">半成品仓</option>
      </select>
      <select v-model="code">
        <option v-for="r in options" :key="r.code" :value="r.code">{{ r.code }} · {{ r.name }}</option>
      </select>
      <input v-model.number="qty" type="number" min="0.001" step="0.001" />
      <button class="btn" @click="adjust">加账</button>
    </div>
    <div v-if="msg" class="kp-ok-banner">{{ msg }}</div>
    <div v-if="error" class="kp-error">{{ error }}</div>
  </div>

  <div class="card">
    <h2 style="margin-top:0">叶料仓</h2>
    <table>
      <thead><tr><th>编码</th><th>名称</th><th>账面</th><th>占用</th><th>可用</th><th>单位</th></tr></thead>
      <tbody>
        <tr v-for="r in leaf" :key="r.id">
          <td>{{ r.code }}</td><td>{{ r.name }}</td><td>{{ r.stock_qty }}</td>
          <td>{{ r.reserved_qty }}</td><td>{{ r.available_qty }}</td><td>{{ r.unit }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card">
    <h2 style="margin-top:0">半成品仓</h2>
    <table>
      <thead><tr><th>编码</th><th>名称</th><th>账面</th><th>单位</th></tr></thead>
      <tbody>
        <tr v-for="r in semi" :key="r.id">
          <td>{{ r.code }}</td><td>{{ r.name }}</td><td>{{ r.stock_qty }}</td><td>{{ r.unit }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
