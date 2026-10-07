<script setup lang="ts">
defineProps<{ node: any }>()
</script>

<template>
  <li>
    <span v-if="node.kind === 'semi'" class="kp-semi-tag">半成品</span>
    {{ node.ingredient }} · {{ node.qty }} {{ node.unit }}
    <span v-if="node.cycle" class="kp-cycle-tag">↻ 成环</span>
    <ul v-if="node.children && node.children.length">
      <BomNode v-for="(c, i) in node.children" :key="i" :node="c" />
    </ul>
  </li>
</template>
