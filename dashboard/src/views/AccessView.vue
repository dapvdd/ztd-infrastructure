<script setup>
import { useRoute, RouterLink } from 'vue-router'
import RoleBadge from '@/components/RoleBadge.vue'
const route = useRoute()
</script>
<template>
  <section class="control-page">
    <p class="eyebrow">Access control / Integration pending</p>
    <h2>{{ route.path === '/users' ? 'User management' : route.path === '/forbidden' ? 'Access unavailable' : 'Sign in' }}</h2>
    <article class="control-card" role="status">
      <h3>Awaiting backend integration</h3>
      <p>Application sessions, user management, and role enforcement are not available on the current backend. This page does not establish that dashboard requests are protected.</p>
      <p>No credentials are collected here. No user identity or permissions are simulated.</p>
      <RouterLink to="/">Return to Operations Overview</RouterLink>
    </article>
    <div class="control-grid">
      <article v-for="role in ['ADMIN', 'OPERATOR', 'VIEWER']" :key="role" class="control-card">
        <RoleBadge :role="role" />
        <p>{{ role === 'ADMIN' ? 'Planned: manage users, security, and device deletion.' : role === 'OPERATOR' ? 'Planned: provision devices and deploy modules.' : 'Planned: monitor permitted devices and operational history.' }}</p>
      </article>
    </div>
    <p>Frontend permissions are presentation only. FastAPI must authorize every protected request.</p>
    <p>Authentication remains disabled until backend session and authorization support and HTTPS are ready.</p>
  </section>
</template>
