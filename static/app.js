// ============================================================
// Flight Monitor — static/app.js
// ============================================================

var state = {
  flights: []
};

function toast(pesan) {
  var el = document.getElementById("toast");
  el.textContent = pesan;
  el.classList.remove("is-hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(function () { el.classList.add("is-hidden"); }, 3200);
}

function setLoading(aktif) {
  document.getElementById("loading").classList.toggle("is-hidden", !aktif);
}

// ---------- util tanggal/waktu ----------
function parseWaktu(str) {
  if (!str) return null;
  var d = new Date(str);
  if (isNaN(d.getTime())) {
    d = new Date(str.replace(" ", "T"));
  }
  return isNaN(d.getTime()) ? null : d;
}

function formatJamMenit(d) {
  if (!d) return "-";
  return d.toLocaleString("id-ID", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit"
  });
}

function formatSisaWaktu(targetDate) {
  var sekarang = new Date();
  var selisihMs = targetDate.getTime() - sekarang.getTime();
  var absMenit = Math.round(Math.abs(selisihMs) / 60000);

  var jam = Math.floor(absMenit / 60);
  var menit = absMenit % 60;
  var teks = jam > 0 ? (jam + " jam " + menit + " mnt") : (menit + " mnt");

  return selisihMs >= 0 ? teks + " lagi" : teks + " yang lalu";
}

// ---------- render daftar flight ----------
var timerTick = null;

function renderFlights() {
  var list = document.getElementById("daftar-flight");
  var kosong = document.getElementById("daftar-kosong");

  if (!state.flights.length) {
    kosong.classList.remove("is-hidden");
    list.innerHTML = "";
    return;
  }
  kosong.classList.add("is-hidden");

  list.innerHTML = "";
  state.flights.forEach(function (f) {
    var card = document.createElement("div");
    card.className = "flight-card";

    var badgeKelas = "status-badge--aktif";
    var badgeTeks = "Terbang";
    if (f.status === "landed") { badgeKelas = "status-badge--landed"; badgeTeks = "Sudah Landing"; }
    else if (f.status === "cancelled") { badgeKelas = "status-badge--cancelled"; badgeTeks = "Dibatalkan"; }
    else if (f.berangkat_aktual) { badgeTeks = "Terbang"; }
    else { badgeTeks = "Dijadwalkan"; }

    var waktuTiba = parseWaktu(f.tiba_estimasi || f.tiba_dijadwalkan);
    var countdownHtml;
    var countdownKelas = "flight-card__countdown";

    if (f.status === "landed") {
      countdownKelas += " selesai";
      var waktuLandingAsli = parseWaktu(f.tiba_aktual) || waktuTiba;
      countdownHtml = '<span class="angka">Sudah mendarat</span>' +
        '<div class="flight-card__waktu">' + (waktuLandingAsli ? formatJamMenit(waktuLandingAsli) : "") + '</div>';
    } else if (f.status === "cancelled") {
      countdownHtml = '<span class="angka">Penerbangan dibatalkan</span>';
    } else if (waktuTiba) {
      countdownHtml = '<span class="angka">' + formatSisaWaktu(waktuTiba) + '</span> menuju landing' +
        '<div class="flight-card__waktu">Estimasi tiba: ' + formatJamMenit(waktuTiba) + '</div>';
    } else {
      countdownHtml = '<span class="angka">Menunggu data jadwal...</span>';
    }

    card.innerHTML =
      '<div class="flight-card__head">' +
        '<div>' +
          '<div class="flight-card__nomor"></div>' +
          '<div class="flight-card__maskapai"></div>' +
        '</div>' +
        '<span class="status-badge ' + badgeKelas + '">' + badgeTeks + '</span>' +
      '</div>' +
      '<div class="flight-card__rute"></div>' +
      '<div class="' + countdownKelas + '">' + countdownHtml + '</div>' +
      '<button class="flight-card__hapus" type="button">berhenti pantau</button>';

    card.querySelector(".flight-card__nomor").textContent = f.nomor;
    card.querySelector(".flight-card__maskapai").textContent = f.maskapai || "-";
    card.querySelector(".flight-card__rute").innerHTML =
      '<strong>' + (f.asal || "?") + '</strong> &rarr; <strong>' + (f.tujuan || "?") + '</strong> &middot; ' + f.tanggal;

    card.querySelector(".flight-card__hapus").addEventListener("click", function () {
      hapusFlight(f.id);
    });

    list.appendChild(card);
  });
}

function mulaiTickCountdown() {
  if (timerTick) clearInterval(timerTick);
  timerTick = setInterval(renderFlights, 30000); // hitung ulang teks "X menit lagi" tiap 30 detik
}

// ---------- ambil daftar dari server ----------
function muatFlights() {
  fetch("/api/flights")
    .then(function (r) { return r.json(); })
    .then(function (json) {
      if (!json.ok) return;
      state.flights = json.data;
      renderFlights();
    })
    .catch(function () { /* diam saja, biar gak ganggu kalau lagi offline sebentar */ });
}

// refresh otomatis dari server tiap 30 detik (ambil update dari cron di background)
setInterval(muatFlights, 30000);

// ---------- tambah flight ----------
document.getElementById("input-tanggal").valueAsDate = new Date();

document.getElementById("form-tambah").addEventListener("submit", function (e) {
  e.preventDefault();
  var nomor = document.getElementById("input-nomor").value.trim();
  var tanggal = document.getElementById("input-tanggal").value;

  if (!nomor) { toast("Isi nomor penerbangan dulu."); return; }

  setLoading(true);
  fetch("/api/flights", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nomor: nomor, tanggal: tanggal })
  })
    .then(function (r) { return r.json(); })
    .then(function (json) {
      setLoading(false);
      if (!json.ok) { toast(json.pesan || "Gagal menambahkan."); return; }

      document.getElementById("input-nomor").value = "";
      muatFlights();
      toast(json.pesan || "Penerbangan " + nomor + " dipantau.");

      // kalau device ini udah punya izin notifikasi, langsung daftarkan
      // flight baru ini juga supaya ikut dapat push
      if (Notification.permission === "granted" && json.data && json.data.id) {
        daftarkanPushKeFlight(json.data.id);
      }
    })
    .catch(function () {
      setLoading(false);
      toast("Tidak bisa menghubungi server.");
    });
});

function hapusFlight(id) {
  fetch("/api/flights/" + id, { method: "DELETE" })
    .then(function (r) { return r.json(); })
    .then(function (json) {
      if (!json.ok) { toast(json.pesan || "Gagal menghapus."); return; }
      muatFlights();
    })
    .catch(function () { toast("Tidak bisa menghubungi server."); });
}

// ---------- notifikasi push ----------
function urlBase64ToUint8Array(base64String) {
  var padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  var base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  var rawData = atob(base64);
  var outputArray = new Uint8Array(rawData.length);
  for (var i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

function daftarkanPushKeFlight(flightId) {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;

  navigator.serviceWorker.ready
    .then(function (reg) { return reg.pushManager.getSubscription().then(function (sub) { return { reg: reg, sub: sub }; }); })
    .then(function (o) {
      if (o.sub) return o.sub;
      return fetch("/api/vapid_public_key").then(function (r) { return r.json(); }).then(function (json) {
        return o.reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(json.key)
        });
      });
    })
    .then(function (sub) {
      return fetch("/api/flights/" + flightId + "/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subscription: sub.toJSON ? sub.toJSON() : sub })
      });
    })
    .catch(function (e) { console.log("Gagal daftar push:", e); });
}

function daftarkanPushKeSemuaFlightAktif() {
  state.flights
    .filter(function (f) { return f.status === "aktif"; })
    .forEach(function (f) { daftarkanPushKeFlight(f.id); });
}

function aktifkanNotifikasi() {
  if (!("Notification" in window)) {
    toast("Browser ini tidak mendukung notifikasi.");
    return;
  }
  Notification.requestPermission().then(function (izin) {
    if (izin === "granted") {
      document.getElementById("notif-banner").classList.add("is-hidden");
      daftarkanPushKeSemuaFlightAktif();
      toast("Notifikasi aktif.");
    } else {
      toast("Izin notifikasi ditolak.");
    }
  });
}

document.getElementById("btn-aktifkan-notif").addEventListener("click", aktifkanNotifikasi);

function cekTampilkanBannerNotif() {
  if (!("Notification" in window)) return;
  if (Notification.permission === "default") {
    document.getElementById("notif-banner").classList.remove("is-hidden");
  }
}

// ---------- init ----------
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/service-worker.js").catch(function (e) {
    console.log("Service worker gagal daftar:", e);
  });
}

cekTampilkanBannerNotif();
muatFlights();
mulaiTickCountdown();
