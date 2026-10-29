<template>
  <div class="about-page">
    <header class="page-header">
      <div>
        <p class="kicker">Tentang platform</p>
        <h2>ZTD Platform</h2>
        <p class="subtitle">Zero Touch Deployment untuk unit IoT berbasis Raspberry Pi.</p>
      </div>
    </header>

    <section class="about-grid">
      <article class="panel">
        <span class="about-tag">Presence</span>
        <h3>Status dari backend</h3>
        <p>
          ONLINE berarti perangkat masih mengontak backend dalam 15 detik terakhir.
          OFFLINE berarti kontak terakhir sudah lebih lama. Dashboard hanya menampilkan
          nilai dari API dan tidak menghitung ulang status secara lokal.
        </p>
      </article>

      <article class="panel">
        <span class="about-tag">Telemetry</span>
        <h3>Satuan tidak ditebak</h3>
        <p>
          Sampel dengan satuan yang dilaporkan ditampilkan sesuai satuannya. Sampel lama
          tanpa metadata satuan tetap tanpa label dan tidak dihitung ke rata-rata resmi.
        </p>
      </article>

      <article class="panel">
        <span class="about-tag">Deployment</span>
        <h3>Desired state via MQTT</h3>
        <p>
          Konfigurasi modul dikirim sebagai desired state. Riwayat event deployment
          terpisah dari status terkini tiap modul, sehingga event lama tidak dianggap
          sebagai kondisi sekarang.
        </p>
      </article>
    </section>

    <section class="panel">
      <div class="panel-heading">
        <h3>Yang belum tersedia</h3>
        <span class="meta-label">Sengaja tidak ditampilkan</span>
      </div>
      <ul class="unavailable-list">
        <li>
          <strong>Devices</strong>
          <span>Halaman khusus belum ada; daftar perangkat tersedia di Fleet Overview.</span>
        </li>
        <li>
          <strong>Rooms</strong>
          <span>Belum ada endpoint Rooms; ringkasan room dihitung dari inventory.</span>
        </li>
        <li>
          <strong>Telemetry (global)</strong>
          <span>Belum ada endpoint telemetry gabungan; grafik per unit ada di Fleet Overview.</span>
        </li>
        <li>
          <strong>MQTT broker health</strong>
          <span>API belum mengekspos health broker, jadi tidak ada badge status palsu.</span>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.about-page {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 22px;
}

.page-header h2 {
  margin: 0 0 6px;
  color: #f8fafc;
  font-size: clamp(1.9rem, 3vw, 2.5rem);
}

.kicker {
  margin: 0 0 8px;
  color: #7dd3fc;
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.subtitle {
  margin: 0;
  color: #94a3b8;
}

.about-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
}

.panel {
  min-width: 0;
  padding: 20px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 18px;
  background: rgba(15, 23, 42, 0.72);
}

.panel h3 {
  margin: 10px 0 8px;
  color: #f8fafc;
}

.panel p {
  margin: 0;
  color: #a5b4c7;
  font-size: 0.86rem;
  line-height: 1.65;
}

.about-tag {
  display: inline-flex;
  padding: 4px 9px;
  border: 1px solid rgba(56, 189, 248, 0.24);
  border-radius: 999px;
  color: #7dd3fc;
  background: rgba(56, 189, 248, 0.1);
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.panel-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.panel-heading h3 {
  margin: 0;
}

.meta-label {
  color: #94a3b8;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.unavailable-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 18px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.unavailable-list li {
  padding: 12px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 12px;
  background: rgba(2, 6, 23, 0.28);
}

.unavailable-list strong,
.unavailable-list span {
  display: block;
}

.unavailable-list strong {
  color: #e2e8f0;
  font-size: 0.85rem;
}

.unavailable-list span {
  margin-top: 4px;
  color: #94a3b8;
  font-size: 0.78rem;
  line-height: 1.55;
}

@media (max-width: 980px) {
  .about-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .unavailable-list {
    grid-template-columns: 1fr;
  }

  .panel-heading {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
