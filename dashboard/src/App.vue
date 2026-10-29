<script setup>
import { RouterLink, RouterView } from 'vue-router'
import './assets/control-plane.css'
</script>

<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">Lewati ke konten</a>
    <aside class="sidebar">
      <div class="brand-block">
        <div class="brand-mark">Z</div>
        <div>
          <div class="eyebrow">edge control</div>
          <h1>ZTD Platform</h1>
        </div>
      </div>

      <nav class="side-nav" aria-label="Navigasi utama">
        <span class="nav-label">Overview</span>
        <RouterLink class="nav-item" exact-active-class="active" to="/">Operations Overview</RouterLink>
        <RouterLink class="nav-item" active-class="active" to="/infrastructure">Infrastructure Health</RouterLink>
        <RouterLink class="nav-item" active-class="active" to="/users">User management · Pending</RouterLink>
        <RouterLink class="nav-item" active-class="active" to="/login">Session integration</RouterLink>
        <RouterLink class="nav-item" active-class="active" to="/deployments">Deployments</RouterLink>
        <RouterLink class="nav-item" active-class="active" to="/modules">Modules</RouterLink>
        <span
          class="nav-item nav-item-disabled"
          aria-disabled="true"
          title="Halaman Devices belum diimplementasikan. Daftar perangkat lengkap ada di Fleet Overview."
        >
          Devices <span class="nav-badge">Belum tersedia</span>
        </span>
        <span
          class="nav-item nav-item-disabled"
          aria-disabled="true"
          title="Belum ada endpoint Rooms di API, jadi halaman ini sengaja dinonaktifkan."
        >
          Rooms <span class="nav-badge">Belum tersedia</span>
        </span>
        <span
          class="nav-item nav-item-disabled"
          aria-disabled="true"
          title="Belum ada endpoint telemetry gabungan. Grafik telemetry per perangkat ada di Fleet Overview."
        >
          Telemetry <span class="nav-badge">Belum tersedia</span>
        </span>
        <p class="nav-note">
          Devices, Rooms, dan Telemetry sengaja dinonaktifkan karena halaman atau endpoint-nya belum
          ada. Data perangkat dan grafik telemetry per unit tetap tersedia di Fleet Overview.
        </p>
        <span class="nav-label">Info</span>
        <RouterLink class="nav-item" active-class="active" to="/about">About</RouterLink>
      </nav>

      <!-- Broker health is not exposed by the API; showing a green "Healthy" badge here
           would be an invented status, so the absence is stated instead. -->
      <div class="sidebar-card sidebar-card-muted">
        <span class="mini-label">MQTT</span>
        <strong>Not monitored</strong>
        <small>No broker health endpoint in the API</small>
      </div>
    </aside>

    <main id="main-content" class="content" tabindex="-1">
      <RouterView :key="$route.fullPath" />
    </main>
  </div>
</template>

<style scoped>
.skip-link {
  position: absolute;
  left: 12px;
  top: -56px;
  z-index: 100;
  padding: 10px 14px;
  border-radius: 10px;
  background: #38bdf8;
  color: #04121f;
  font-size: 0.85rem;
  font-weight: 800;
  text-decoration: none;
  transition: top 0.18s ease;
}

.skip-link:focus {
  top: 12px;
}

.app-shell {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  min-height: 100vh;
  overflow-x: clip;
  background: linear-gradient(180deg, #09111f 0%, #0d1729 100%);
}

.sidebar {
  background: rgba(15, 23, 42, 0.9);
  border-right: 1px solid rgba(148, 163, 184, 0.18);
  padding: 28px 20px;
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 32px;
}

.brand-mark {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #38bdf8, #8b5cf6);
  color: white;
  font-weight: 800;
  font-size: 1.2rem;
}

.eyebrow {
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: #7dd3fc;
}

.brand-block h1 {
  margin: 4px 0 0;
  font-size: 1.05rem;
  color: #e2e8f0;
}

.side-nav {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.nav-label {
  font-size: 0.68rem;
  font-weight: 700;
  color: #94a3b8;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  margin: 10px 0 6px;
}

.nav-item {
  color: #cbd5e1;
  text-decoration: none;
  padding: 10px 12px;
  border-radius: 10px;
  display: block;
  transition: 0.2s ease;
}

.nav-item.active,
.nav-item:hover {
  background: rgba(56, 189, 248, 0.12);
  color: #f8fafc;
}

.nav-item-disabled {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  cursor: not-allowed;
  opacity: 0.55;
}

.nav-badge {
  flex: 0 0 auto;
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.16);
  color: #cbd5e1;
  font-size: 0.6rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.nav-note {
  margin: 4px 0 0;
  color: #94a3b8;
  font-size: 0.7rem;
  line-height: 1.5;
}

.sidebar-card {
  margin-top: 28px;
  background: rgba(15, 118, 110, 0.16);
  border: 1px solid rgba(45, 212, 191, 0.18);
  border-radius: 16px;
  padding: 16px;
  color: #d1fae5;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sidebar-card-muted {
  background: rgba(148, 163, 184, 0.1);
  border-color: rgba(148, 163, 184, 0.22);
  color: #cbd5e1;
}

.sidebar-card strong {
  font-size: 1.1rem;
}

.sidebar-card small {
  color: #a7f3d0;
}

.sidebar-card-muted small {
  color: #94a3b8;
}

.mini-label {
  font-size: 0.68rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  opacity: 0.8;
}

.content {
  min-width: 0;
  padding: 28px;
}

@media (max-width: 900px) {
  .app-shell {
    grid-template-columns: minmax(0, 1fr);
  }

  .sidebar {
    padding: 14px 16px 10px;
    border-right: none;
    border-bottom: 1px solid rgba(148, 163, 184, 0.18);
  }

  .brand-block {
    margin-bottom: 12px;
  }

  .brand-mark {
    width: 36px;
    height: 36px;
    border-radius: 12px;
    font-size: 1rem;
  }

  .side-nav {
    flex-direction: row;
    align-items: center;
    gap: 5px;
    overflow-x: auto;
    padding-bottom: 4px;
    scrollbar-width: thin;
  }

  .nav-label,
  .nav-note,
  .sidebar-card {
    display: none;
  }

  .nav-item {
    flex: 0 0 auto;
    padding: 8px 10px;
    font-size: 0.84rem;
    white-space: nowrap;
  }

  .nav-item-disabled {
    opacity: 0.52;
  }

  .nav-badge {
    padding: 2px 5px;
    font-size: 0.54rem;
  }

  .content {
    padding: 20px 16px 30px;
  }
}
</style>
