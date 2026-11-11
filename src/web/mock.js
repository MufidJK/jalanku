// Balasan palsu sesuai "Kontrak data" (versi_kontrak 1).
// Dipakai kalau URL berisi ?mock=1.

const SKENARIO_MOCK = [
  {
    peringatan: null,
    objek: [],
    jalur: { status: "terbuka", persen_jalan: 0.46 },
  },
  {
    peringatan: {
      pesan: "Orang di kiri",
      kelas: "orang",
      posisi: "kiri",
      jarak: "sedang",
      tingkat: 1,
    },
    objek: [
      { kelas: "orang", conf: 0.64, kotak: [0.05, 0.4, 0.2, 0.8], posisi: "kiri", jarak: "sedang" },
    ],
    jalur: { status: "terbuka", persen_jalan: 0.5 },
  },
  {
    peringatan: {
      pesan: "Pilar di depan, sedang",
      kelas: "pilar",
      posisi: "tengah",
      jarak: "sedang",
      tingkat: 2,
    },
    objek: [
      { kelas: "pilar", conf: 0.71, kotak: [0.42, 0.3, 0.58, 0.85], posisi: "tengah", jarak: "sedang" },
    ],
    jalur: { status: "terhalang", persen_jalan: 0.3 },
  },
  {
    peringatan: {
      pesan: "Tangga di depan",
      kelas: "tangga",
      posisi: "tengah",
      jarak: "dekat",
      tingkat: 3,
    },
    objek: [
      { kelas: "tangga", conf: 0.82, kotak: [0.2, 0.55, 0.8, 0.98], posisi: "tengah", jarak: "dekat" },
      { kelas: "orang", conf: 0.6, kotak: [0.7, 0.35, 0.9, 0.8], posisi: "kanan", jarak: "sedang" },
    ],
    jalur: { status: "terhalang", persen_jalan: 0.12 },
  },
];

const DURASI_SKENARIO_MS = 3000;

async function ambilMock() {
  // pura-pura menunggu server sebentar (20-60 ms)
  await new Promise((r) => setTimeout(r, 20 + Math.random() * 40));
  const i = Math.floor(Date.now() / DURASI_SKENARIO_MS) % SKENARIO_MOCK.length;
  const s = SKENARIO_MOCK[i];
  return {
    versi_kontrak: 1,
    waktu_ms: 38,
    peringatan: s.peringatan,
    objek: s.objek,
    jalur: s.jalur,
  };
}