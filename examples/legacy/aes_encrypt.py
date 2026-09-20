from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad
import hashlib

# =========================
# 원본 파일 읽기
# =========================

with open("input.txt", "rb") as f:
    data = f.read()

# =========================
# SHA-256 HASH 생성
# =========================

sha256_hash = hashlib.sha256(data).hexdigest()

print("SHA-256 HASH:")
print(sha256_hash)

# hash 저장
with open("hash.txt", "w") as f:
    f.write(sha256_hash)

# =========================
# AES-256 키 생성
# =========================

key = get_random_bytes(32)

# 키 저장
with open("key.bin", "wb") as f:
    f.write(key)

# =========================
# AES 암호화
# =========================

cipher = AES.new(key, AES.MODE_CBC)

ciphertext = cipher.encrypt(
    pad(data, AES.block_size)
)

# 암호문 저장
with open("encrypted.bin", "wb") as f:
    f.write(cipher.iv)
    f.write(ciphertext)

print("암호화 완료")
print("encrypted.bin 생성 완료")