<script setup>
defineProps({ allowed: { type: Boolean, default: false }, reason: { type: String, default: 'Permission unavailable; backend integration required' } })
</script>
<template><span><slot v-if="allowed" /><span v-else role="status">{{ reason }}</span></span></template>
