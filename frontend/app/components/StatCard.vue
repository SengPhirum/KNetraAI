<template>
  <div class="card">
    <div style="font-size: 0.85rem; color: #64748b;">{{ label }}</div>
    <div style="font-size: 2rem; font-weight: 800; margin-top: 0.25rem;">{{ value ?? 0 }}</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ label: string, value: number | string | null | undefined }>()
</script>
