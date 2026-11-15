// Koneksi ke server Nicksen (kontrak data v1).
// Kalau halaman dibuka dari server Nicksen, alamatnya relatif (kosong).
// Untuk tes dari tempat lain: ?server=https://<ip-laptop>:8000
const PARAM = new URLSearchParams(location.search);
const ALAMAT_SERVER = (PARAM.get("server") || "").replace(/\/$/, "");
const WAKTU_HABIS_MS = 3000;
const SESI = Math.random().toString(36).slice(2, 10);
let serverBermasalah = false;

function tandaiServerBermasalah(alasan) {
  setStatus("Server bermasalah", null, alasan);
  setZona(null, 0);
  gambarOverlay(null);
  if (!serverBermasalah) {
    serverBermasalah = true;
    ucapkan({ pesan: "Server bermasalah", tingkat: 2 }); // diucapkan sekali
  }
}

async function kirimKeServer(jpeg) {
  const kontrol = new AbortController();
  const batas = setTimeout(() => kontrol.abort(), WAKTU_HABIS_MS);
  try {
    const res = await fetch(ALAMAT_SERVER + "/api/deteksi", {
      method: "POST",
      headers: { "Content-Type": "image/jpeg", "X-Sesi": SESI },
      body: jpeg,
      signal: kontrol.signal,
    });
    if (!res.ok) {
      tandaiServerBermasalah("Kode " + res.status);
      return null;
    }
    const data = await res.json();
    if (data.versi_kontrak !== 1) {
      tandaiServerBermasalah("Versi kontrak tidak cocok");
      return null;
    }
    serverBermasalah = false;
    return data;
  } catch (err) {
    tandaiServerBermasalah(
      err.name === "AbortError" ? "Server terlalu lambat" : "Tidak tersambung"
    );
    return null;
  } finally {
    clearTimeout(batas);
  }
}