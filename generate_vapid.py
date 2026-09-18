# ============================================================
# Jalankan sekali aja: python3.10 generate_vapid.py
#
# Ini bikin file "vapid_private.pem" di folder yang sama, dan
# nyetak "VAPID_PUBLIC_KEY" yang harus kamu copy ke app.py.
# ============================================================

import base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

private_key = ec.generate_private_key(ec.SECP256R1())
public_key = private_key.public_key()

private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)

numbers = public_key.public_numbers()
x = numbers.x.to_bytes(32, "big")
y = numbers.y.to_bytes(32, "big")
raw_public = b"\x04" + x + y  # format "uncompressed point", 65 byte

public_b64 = base64.urlsafe_b64encode(raw_public).rstrip(b"=").decode()

with open("vapid_private.pem", "wb") as f:
    f.write(private_pem)

print("")
print("=" * 60)
print("Berhasil. File vapid_private.pem sudah dibuat di folder ini.")
print("Sekarang copy baris di bawah ini ke app.py:")
print("")
print('VAPID_PUBLIC_KEY = "' + public_b64 + '"')
print("=" * 60)
