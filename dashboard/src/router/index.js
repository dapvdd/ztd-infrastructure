import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import DeploymentsView from '../views/DeploymentsView.vue'
import ModulesView from '../views/ModulesView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/devices/:deviceId', name: 'device', component: () => import('../views/DeviceView.vue') },
    { path: '/infrastructure', component: () => import('../views/InfrastructureView.vue') },
    { path: '/login', component: () => import('../views/AccessView.vue') },
    { path: '/users', component: () => import('../views/AccessView.vue') },
    { path: '/forbidden', component: () => import('../views/AccessView.vue') },
    {
      path: '/',
      name: 'home',
      component: HomeView,
    },
    {
      path: '/deployments',
      name: 'deployments',
      component: DeploymentsView,
    },
    {
      path: '/modules',
      name: 'modules',
      component: ModulesView,
    },
    {
      path: '/about',
      name: 'about',
      // route level code-splitting
      // this generates a separate chunk (About.[hash].js) for this route
      // which is lazy-loaded when the route is visited.
      component: () => import('../views/AboutView.vue'),
    },
  ],
})

export default router
