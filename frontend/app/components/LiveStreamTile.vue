<template>
  <div ref="tileRef" class="stream-tile" :class="{ fullscreen: isFullscreen }">
    <img v-if="src && !errored" :src="cacheBustedSrc" :alt="camera?.name" @error="onError" @load="errored = false" />
    <img v-else-if="fallbackImage" :src="fallbackImage" :alt="camera?.name" class="fallback" />
    <div v-else class="placeholder"><span>{{ errored ? 'Reconnecting...' : fallbackText }}</span></div>

    <span v-if="src && !errored" class="live-dot">LIVE</span>
    <button v-if="src" class="fullscreen-btn" type="button" :title="isFullscreen ? 'Exit fullscreen' : 'Fullscreen'" @click.stop="toggleFullscreen">
      {{ isFullscreen ? '⤡' : '⤢' }}
    </button>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{
  camera?: any
  src?: string | null
  fallbackImage?: string | null
  fallbackText?: string
}>()

const tileRef = ref<HTMLElement | null>(null)
const errored = ref(false)
const isFullscreen = ref(false)
const retryToken = ref(0)
let retryTimer: ReturnType<typeof setTimeout> | null = null

const cacheBustedSrc = computed(() => {
  if (!props.src) return ''
  if (!retryToken.value) return props.src
  const sep = props.src.includes('?') ? '&' : '?'
  return `${props.src}${sep}_r=${retryToken.value}`
})

const onError = () => {
  errored.value = true
  if (retryTimer) clearTimeout(retryTimer)
  retryTimer = setTimeout(() => {
    retryToken.value += 1
    errored.value = false
  }, 2500)
}

const toggleFullscreen = async () => {
  if (!tileRef.value) return
  if (!document.fullscreenElement) {
    await tileRef.value.requestFullscreen?.()
  } else {
    await document.exitFullscreen?.()
  }
}

const onFullscreenChange = () => {
  isFullscreen.value = document.fullscreenElement === tileRef.value
}

onMounted(() => document.addEventListener('fullscreenchange', onFullscreenChange))
onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  if (retryTimer) clearTimeout(retryTimer)
})

watch(() => props.src, () => {
  errored.value = false
  retryToken.value = 0
})
</script>

<style scoped>
.stream-tile {
  position: relative;
  width: 100%;
  height: 100%;
  background: #020617;
  overflow: hidden;
  display: grid;
  place-items: center;
}

.stream-tile img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.stream-tile.fullscreen {
  background: #000;
}

.placeholder {
  color: #94a3b8;
  font-size: 0.85rem;
  text-align: center;
  padding: 1rem;
}

.live-dot {
  position: absolute;
  top: 0.5rem;
  left: 0.5rem;
  background: rgba(185, 28, 28, 0.9);
  color: white;
  font-size: 0.65rem;
  font-weight: 700;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  letter-spacing: 0.05em;
}

.fullscreen-btn {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  background: rgba(15, 23, 42, 0.65);
  color: white;
  border: 0;
  border-radius: 0.4rem;
  width: 1.8rem;
  height: 1.8rem;
  display: grid;
  place-items: center;
  cursor: pointer;
  font-size: 0.95rem;
  line-height: 1;
}

.fullscreen-btn:hover {
  background: rgba(15, 23, 42, 0.85);
}
</style>
