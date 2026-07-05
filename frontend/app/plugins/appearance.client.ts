export default defineNuxtPlugin(async () => {
  const { refresh } = useAppearance()
  await refresh()
})
