<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import BomNode from '../components/BomNode.vue'

const tree = ref<any[]>([])
onMounted(async () => { tree.value = await api('/bom/tree') })
</script>

<template>
  <h1>BOM 树</h1>
  <p class="sub">菜品用料树 · 半成品可再挂叶原料 · 生产厨房口径</p>
  <div class="kp-bom-tree" style="max-width:420px">
    <h2>菜品 / BOM</h2>
    <div v-for="d in tree" :key="d.code" class="kp-dish-node">
      <strong>{{ d.dish }}</strong>
      <span style="font-size:0.7rem;color:#8a8078">{{ d.code }}</span>
      <ul>
        <BomNode v-for="(c, i) in d.children" :key="i" :node="c" />
      </ul>
    </div>
  </div>
</template>
