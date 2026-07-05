export default defineNuxtRouteMiddleware((to) => {
  if (!process.client) return
  if (to.path === '/login') return
  const token = localStorage.getItem('token')
  if (!token) return navigateTo('/login')
})
