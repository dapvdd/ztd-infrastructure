<script setup>
defineProps({ role: { type: String, required: true } })
</script>
<template><span class="role-badge">{{ role }}</span></template>
