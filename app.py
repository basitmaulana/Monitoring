# ============================================================
# Flight Monitor — app.py
#
# Pantau beberapa nomor penerbangan sekaligus, dapat notifikasi
# (lewat status bar HP) begitu salah satunya landing.
#
# CARA ISI PENGATURAN DI BAWAH INI (WAJIB sebelum dipakai):
#   1. AERODATABOX_API_KEY -> daftar gratis di RapidAPI, cari
#      "AeroDataBox", subscribe ke plan gratisnya, copy API key-nya.
#   2. VAPID_PUBLIC_KEY & VAPID_PRIVATE_KEY_PATH -> generate sekali
#      pakai script yang ada di PANDUAN.md, taruh file
#      vapid_private.pem di folder yang sama dengan app.py ini.
#   3. CRON_KUNCI -> ganti jadi kata sandi acak bikinan sendiri.
#      Ini dipakai di URL supaya cuma layanan cron kamu yang bisa
#      memicu pengecekan (bukan sembarang orang di internet).
# ============================================================

from flask import Flask, render_template, request, jsonify, send_from_directory
import json
import os
import uuid
import requests
from datetime import datetime, timedelta, timezone

try:
    from pywebpush import webpush, WebPushException
except ImportError:
    webpush = None
    WebPushException = Exception


APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
FLIGHTS_FILE = os.path.join(DATA_DIR, "flights.json")

app = Flask(__name__)

# ---------------- ISI BAGIAN INI ----------------
AERODATABOX_API_KEY = "ISI_API_KEY_RAPIDAPI_DI_SINI"
AERODATABOX_HOST = "aerodatabox.p.rapidapi.com"

VAPID_PUBLIC_KEY = "ISI_SETELAH_GENERATE_VAPID"
VAPID_PRIVATE_KEY_PATH = os.path.join(APP_DIR, "vapid_private.pem")
VAPID_CLAIMS_SUB = "mailto:ganti@dengan-email-kamu.com"

CRON_KUNCI = "ganti-dengan-kata-sandi-acak-punya-sendiri"
# --------------------------------------------------


# ---------------- penyimpanan data (file JSON) ----------------
def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_flights():
    return load_json(FLIGHTS_FILE, [])


def save_flights(data):
    save_json(FLIGHTS_FILE, data)


# ---------------- panggil AeroDataBox ----------------
def _ambil_waktu(obj, *kunci_kunci):
    """AeroDataBox kadang pakai nama field waktu yang beda-beda
    tergantung status penerbangan (scheduledTime/predictedTime/
    actualTime/revisedTime). Coba beberapa kemungkinan berurutan."""
    if not obj:
        return None
    for kunci in kunci_kunci:
        nilai = obj.get(kunci)
        if nilai:
            if isinstance(nilai, dict):
                return nilai.get("local") or nilai.get("utc")
            return nilai
    return None


def rapikan_data_flight(f):
    berangkat = f.get("departure") or {}
    tiba = f.get("arrival") or {}
    airline = f.get("airline") or {}

    kualitas_tiba = tiba.get("quality") or []
    tiba_live = "Live" in kualitas_tiba

    return {
        "maskapai": airline.get("name") or "",
        "asal": (berangkat.get("airport") or {}).get("iata")
        or (berangkat.get("airport") or {}).get("name") or "",
        "tujuan": (tiba.get("airport") or {}).get("iata")
        or (tiba.get("airport") or {}).get("name") or "",
        "status_mentah": (f.get("status") or "").strip(),
        "berangkat_dijadwalkan": _ambil_waktu(berangkat, "scheduledTime"),
        "berangkat_aktual": _ambil_waktu(berangkat, "actualTime", "runwayTime"),
        "tiba_dijadwalkan": _ambil_waktu(tiba, "scheduledTime"),
        "tiba_estimasi": _ambil_waktu(tiba, "predictedTime", "revisedTime", "scheduledTime"),
        "tiba_aktual": _ambil_waktu(tiba, "actualTime", "runwayTime"),
        "tiba_live": tiba_live,
    }


def cari_status_flight(nomor, tanggal):
    """Panggil AeroDataBox buat 1 nomor+tanggal penerbangan.
    Return dict data yang sudah dirapikan, atau None kalau gagal/nihil."""
    nomor = nomor.strip().upper().replace(" ", "")
    url = f"https://{AERODATABOX_HOST}/flights/number/{nomor}/{tanggal}"
    headers = {
        "X-RapidAPI-Key": AERODATABOX_API_KEY,
        "X-RapidAPI-Host": AERODATABOX_HOST,
    }
    params = {"withAircraftImage": "false", "withLocation": "false"}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        hasil = r.json()
    except Exception as e:
        print("Gagal panggil AeroDataBox:", e)
        return None

    if not hasil or not isinstance(hasil, list) or len(hasil) == 0:
        return None

    return rapikan_data_flight(hasil[0])


def sudah_landing(status_mentah, data):
    status_l = (status_mentah or "").lower()
    if any(k in status_l for k in ["landed", "arrived"]):
        return True
    if data.get("tiba_aktual"):
        return True
    return False


def sudah_cancel(status_mentah):
    return "cancel" in (status_mentah or "").lower()


# ---------------- Web Push ----------------
def _kirim_payload(subscription_info, payload_json):
    """Kirim 1 payload ke 1 subscription. True kalau sukses (subscription
    masih valid), False kalau subscription harus dibuang (kadaluarsa)."""
    if webpush is None:
        print("pywebpush belum ter-install, push dilewati.")
        return True
    try:
        webpush(
            subscription_info=subscription_info,
            data=payload_json,
            vapid_private_key=VAPID_PRIVATE_KEY_PATH,
            vapid_claims={"sub": VAPID_CLAIMS_SUB},
        )
        return True
    except WebPushException as e:
        print("Push gagal, subscription dibuang:", e)
        return False
    except Exception as e:
        print("Push error (dianggap sesaat, subscription tetap disimpan):", e)
        return True


def kirim_push(entri, judul, isi, penting=True):
    """penting=True -> notifikasi 'tegas' (bunyi/getar), dipakai pas landing.
    penting=False -> notifikasi 'diam-diam' yang MENIMPA notifikasi lama
    (tag sama), dipakai buat update berkala (estimasi berubah dsb) supaya
    status bar-nya kelihatan 'hidup' terus tanpa nge-spam bunyi tiap 5 menit."""
    payload = json.dumps({
        "title": judul,
        "body": isi,
        "nomor": entri["nomor"],
        "silent": not penting,
    })

    sisa = []
    for sub in entri.get("push_subscriptions", []):
        if _kirim_payload(sub, payload):
            sisa.append(sub)
    entri["push_subscriptions"] = sisa


def kirim_push_ke_satu_subscription(subscription, entri):
    """Dipakai pas device baru pertama kali subscribe ke 1 flight -- biar
    langsung ada notifikasi 'sedang dipantau' di status bar, gak perlu
    nunggu siklus cron berikutnya."""
    waktu = entri.get("tiba_estimasi") or entri.get("tiba_dijadwalkan")
    judul = f"{entri['nomor']} sedang dipantau"
    isi = f"{entri.get('asal') or '?'} -> {entri.get('tujuan') or '?'}"
    if waktu:
        isi += f" | estimasi tiba {waktu}"
        if not entri.get("tiba_live"):
            isi += " (berdasarkan jadwal, belum live)"
    payload = json.dumps({"title": judul, "body": isi, "nomor": entri["nomor"], "silent": True})
    _kirim_payload(subscription, payload)


# ---------------- routes: halaman & PWA shell ----------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/manifest.json")
def manifest():
    return send_from_directory(os.path.join(APP_DIR, "static"), "manifest.json")


@app.route("/service-worker.js")
def service_worker():
    return send_from_directory(os.path.join(APP_DIR, "static"), "service-worker.js")


# ---------------- routes: API ----------------
@app.route("/api/vapid_public_key")
def api_vapid_public_key():
    return jsonify({"key": VAPID_PUBLIC_KEY})


@app.route("/api/flights", methods=["GET"])
def api_flights_list():
    data = load_flights()
    ringkas = []
    for f in data:
        salinan = dict(f)
        salinan.pop("push_subscriptions", None)
        ringkas.append(salinan)

    def kunci_urut(f):
        selesai = 1 if f.get("status") in ("landed", "cancelled") else 0
        waktu = f.get("tiba_estimasi") or f.get("tiba_dijadwalkan") or f.get("berangkat_dijadwalkan") or ""
        return (selesai, waktu)

    ringkas.sort(key=kunci_urut)
    return jsonify({"ok": True, "data": ringkas})


@app.route("/api/flights", methods=["POST"])
def api_flights_tambah():
    body = request.get_json(force=True, silent=True) or {}
    nomor = (body.get("nomor") or "").strip().upper().replace(" ", "")
    tanggal = (body.get("tanggal") or "").strip() or datetime.now().strftime("%Y-%m-%d")

    if not nomor:
        return jsonify({"ok": False, "pesan": "Nomor penerbangan wajib diisi."}), 400

    data = load_flights()

    sudah_ada = next((f for f in data if f["nomor"] == nomor and f["tanggal"] == tanggal), None)
    if sudah_ada:
        salinan = dict(sudah_ada)
        salinan.pop("push_subscriptions", None)
        return jsonify({"ok": True, "data": salinan, "pesan": "Penerbangan ini sudah dipantau."})

    hasil = cari_status_flight(nomor, tanggal)
    if not hasil:
        return jsonify({
            "ok": False,
            "pesan": "Data penerbangan tidak ditemukan. Cek lagi nomor & tanggalnya, atau coba beberapa saat lagi."
        }), 404

    status_awal = "aktif"
    if sudah_landing(hasil["status_mentah"], hasil):
        status_awal = "landed"
    elif sudah_cancel(hasil["status_mentah"]):
        status_awal = "cancelled"

    entri = {
        "id": uuid.uuid4().hex[:10],
        "nomor": nomor,
        "tanggal": tanggal,
        "maskapai": hasil["maskapai"],
        "asal": hasil["asal"],
        "tujuan": hasil["tujuan"],
        "status": status_awal,
        "berangkat_dijadwalkan": hasil["berangkat_dijadwalkan"],
        "berangkat_aktual": hasil["berangkat_aktual"],
        "tiba_dijadwalkan": hasil["tiba_dijadwalkan"],
        "tiba_estimasi": hasil["tiba_estimasi"],
        "tiba_aktual": hasil["tiba_aktual"],
        "tiba_live": hasil.get("tiba_live", False),
        "terakhir_dicek": datetime.now(timezone.utc).isoformat(),
        "sudah_notif_landing": status_awal == "landed",
        "push_subscriptions": [],
    }
    data.append(entri)
    save_flights(data)

    salinan = dict(entri)
    salinan.pop("push_subscriptions", None)
    return jsonify({"ok": True, "data": salinan})


@app.route("/api/flights/<flight_id>", methods=["DELETE"])
def api_flights_hapus(flight_id):
    data = load_flights()
    baru = [f for f in data if f["id"] != flight_id]
    if len(baru) == len(data):
        return jsonify({"ok": False, "pesan": "Data tidak ditemukan."}), 404
    save_flights(baru)
    return jsonify({"ok": True})


@app.route("/api/flights/<flight_id>/subscribe", methods=["POST"])
def api_flights_subscribe(flight_id):
    body = request.get_json(force=True, silent=True) or {}
    subscription = body.get("subscription")
    if not subscription or not subscription.get("endpoint"):
        return jsonify({"ok": False, "pesan": "Data subscription tidak valid."}), 400

    data = load_flights()
    entri = next((f for f in data if f["id"] == flight_id), None)
    if not entri:
        return jsonify({"ok": False, "pesan": "Penerbangan tidak ditemukan."}), 404

    daftar = entri.setdefault("push_subscriptions", [])
    if not any(s.get("endpoint") == subscription["endpoint"] for s in daftar):
        daftar.append(subscription)
        save_flights(data)
        if entri.get("status") == "aktif":
            kirim_push_ke_satu_subscription(subscription, entri)

    return jsonify({"ok": True})


@app.route("/api/cron/cek")
def api_cron_cek():
    """Dipanggil berkala oleh layanan cron dari luar (mis. cron-job.org).
    Cek status tiap flight yang masih aktif, kirim push kalau ada yang
    baru landing. URL: /api/cron/cek?kunci=RAHASIA_DI_APP_PY"""
    if request.args.get("kunci", "") != CRON_KUNCI:
        return jsonify({"ok": False, "pesan": "Kunci salah."}), 403

    data = load_flights()
    dicek = 0
    berubah = False

    for entri in data:
        if entri.get("status") in ("landed", "cancelled"):
            continue

        hasil = cari_status_flight(entri["nomor"], entri["tanggal"])
        dicek += 1
        if not hasil:
            continue

        status_sebelum = entri.get("status")

        entri["maskapai"] = hasil["maskapai"] or entri.get("maskapai")
        entri["asal"] = hasil["asal"] or entri.get("asal")
        entri["tujuan"] = hasil["tujuan"] or entri.get("tujuan")
        entri["berangkat_dijadwalkan"] = hasil["berangkat_dijadwalkan"] or entri.get("berangkat_dijadwalkan")
        entri["berangkat_aktual"] = hasil["berangkat_aktual"] or entri.get("berangkat_aktual")
        entri["tiba_dijadwalkan"] = hasil["tiba_dijadwalkan"] or entri.get("tiba_dijadwalkan")
        entri["tiba_estimasi"] = hasil["tiba_estimasi"] or entri.get("tiba_estimasi")
        entri["tiba_aktual"] = hasil["tiba_aktual"] or entri.get("tiba_aktual")
        entri["tiba_live"] = hasil.get("tiba_live", entri.get("tiba_live", False))
        entri["terakhir_dicek"] = datetime.now(timezone.utc).isoformat()

        catatan_sumber = "" if entri["tiba_live"] else " (berdasarkan jadwal, belum live)"

        if sudah_landing(hasil["status_mentah"], hasil):
            entri["status"] = "landed"
            if not entri.get("sudah_notif_landing"):
                kirim_push(
                    entri,
                    judul=f"{entri['nomor']} sudah mendarat",
                    isi=f"{entri.get('asal') or '?'} -> {entri.get('tujuan') or '?'}",
                    penting=True,
                )
                entri["sudah_notif_landing"] = True
        elif sudah_cancel(hasil["status_mentah"]):
            entri["status"] = "cancelled"
            if status_sebelum != "cancelled":
                kirim_push(
                    entri,
                    judul=f"{entri['nomor']} dibatalkan",
                    isi=f"{entri.get('asal') or '?'} -> {entri.get('tujuan') or '?'}",
                    penting=True,
                )
        else:
            entri["status"] = "aktif"
            # dikirim TIAP siklus cron (bukan cuma pas berubah) -- ini yang
            # bikin notifikasi kelihatan "standby"/hidup terus di status bar
            # selama flight masih dipantau. Tetap "diam" (gak bunyi/getar),
            # cuma nimpa isi notifikasi lama (tag sama di service worker).
            if entri.get("tiba_estimasi"):
                kirim_push(
                    entri,
                    judul=f"{entri['nomor']} sedang dipantau",
                    isi=f"Estimasi tiba: {entri.get('tiba_estimasi')}{catatan_sumber}",
                    penting=False,
                )

        berubah = True

    # beres-beres data lama (lebih dari 3 hari) biar file gak numpuk
    batas = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    sebelum = len(data)
    data = [f for f in data if f["tanggal"] >= batas]
    if len(data) != sebelum:
        berubah = True

    if berubah:
        save_flights(data)

    return jsonify({"ok": True, "dicek": dicek, "total": len(data)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
