from Crypto.Cipher import AES
import hashlib
import json

# =========================
# 1. AES 비밀키 읽기
# =========================

with open("aes_key.bin", "rb") as f:
    key = f.read()

# =========================
# 2. 암호화 파일 읽기
# =========================

with open("encrypted.bin", "rb") as f:
    encrypted_data = f.read()

# GCM nonce = 16바이트
nonce = encrypted_data[:16]

# tag = 16바이트
tag = encrypted_data[16:32]

# 나머지 = ciphertext
ciphertext = encrypted_data[32:]

# =========================
# 3. AES-256-GCM 복호화
# =========================

try:
    cipher = AES.new(
        key,
        AES.MODE_GCM,
        nonce=nonce
    )

    plaintext = cipher.decrypt_and_verify(
        ciphertext,
        tag
    )

except ValueError:
    print("복호화 실패")
    print("데이터가 변조되었거나 잘못된 키입니다.")
    exit()

# =========================
# 4. 복호화 결과 저장
# =========================

with open("decrypted.json", "wb") as f:
    f.write(plaintext)

print("복호화 완료")
print("decrypted.json 생성 완료")

# =========================
# 5. SHA-256 무결성 검증
# =========================

# 복호화된 데이터의 HASH
decrypted_hash = hashlib.sha256(plaintext).hexdigest()

print("\n복호화 데이터 SHA-256:")
print(decrypted_hash)

# 원본 sample JSON을 동일한 방식으로 직렬화
with open("sample_medical_data.json", "r", encoding="utf-8") as f:
    original_data = json.load(f)

original_bytes = json.dumps(
    original_data,
    ensure_ascii=False,
    separators=(",", ":")
).encode("utf-8")

original_hash = hashlib.sha256(original_bytes).hexdigest()

print("\n원본 데이터 SHA-256:")
print(original_hash)

# =========================
# 6. HASH 비교
# =========================

if decrypted_hash == original_hash:
    print("\n무결성 검증 성공")
    print("복호화된 데이터가 원본과 일치합니다.")
else:
    print("\n무결성 검증 실패")
    print("데이터가 변조되었거나 암호화 과정과 데이터가 다릅니다.")