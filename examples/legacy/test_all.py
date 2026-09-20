import json
import hashlib

from Crypto.Cipher import AES
from key_manager import encrypt_aes_key, decrypt_aes_key


# ==========================================
# 1. 원본 의료데이터 읽기
# ==========================================

with open("sample_medical_data.json", "r", encoding="utf-8") as f:
    original_data = json.load(f)

original_bytes = json.dumps(
    original_data,
    ensure_ascii=False,
    separators=(",", ":")
).encode("utf-8")


# ==========================================
# 2. AES Key 읽기
# ==========================================

with open("aes_key.bin", "rb") as f:
    original_aes_key = f.read()

print("[1] AES Key 확인")
print("    길이:", len(original_aes_key), "bytes")


# ==========================================
# 3. RSA로 AES Key 암호화
# ==========================================

encrypt_aes_key(original_aes_key)

with open("encrypted_key.bin", "rb") as f:
    encrypted_key = f.read()

print("[2] AES Key RSA 암호화 성공")


# ==========================================
# 4. RSA로 AES Key 복구
# ==========================================

recovered_aes_key = decrypt_aes_key(encrypted_key)

if original_aes_key == recovered_aes_key:
    print("[3] AES Key 복구 성공")
else:
    print("[3] ❌ AES Key 복구 실패")
    exit()


# ==========================================
# 5. 암호화된 의료데이터 읽기
# ==========================================

with open("encrypted.bin", "rb") as f:
    encrypted_data = f.read()

# medical_encryptor.py 구조
# nonce + tag + ciphertext

nonce = encrypted_data[:16]
tag = encrypted_data[16:32]
ciphertext = encrypted_data[32:]


# ==========================================
# 6. 복구한 AES Key로 의료데이터 복호화
# ==========================================

try:
    cipher = AES.new(
        recovered_aes_key,
        AES.MODE_GCM,
        nonce=nonce
    )

    decrypted_data = cipher.decrypt_and_verify(
        ciphertext,
        tag
    )

    print("[4] 의료데이터 AES 복호화 성공")

except ValueError:
    print("[4] ❌ 복호화 실패")
    print("    데이터가 변조되었거나 AES Key가 잘못되었습니다.")
    exit()


# ==========================================
# 7. 원본 데이터와 비교
# ==========================================

if decrypted_data == original_bytes:
    print("[5] 원본 의료데이터 일치 ✅")
else:
    print("[5] ❌ 원본 의료데이터 불일치")
    exit()


# ==========================================
# 8. SHA-256 검증
# ==========================================

encrypted_hash = hashlib.sha256(encrypted_data).hexdigest()

with open("hash.txt", "r", encoding="utf-8") as f:
    saved_hash = f.read().strip()

print("[6] SHA-256 검증")

if encrypted_hash == saved_hash:
    print("    SHA-256 일치 ✅")
else:
    print("    ❌ SHA-256 불일치")
    exit()


# ==========================================
# 최종 결과
# ==========================================

print()
print("====================================")
print("      전체 암호화 테스트 성공 ✅")
print("====================================")
print("AES-256-GCM 암호화       : 성공")
print("RSA-OAEP AES Key 보호    : 성공")
print("RSA AES Key 복구         : 성공")
print("의료데이터 복호화        : 성공")
print("원본 데이터 검증         : 성공")
print("SHA-256 무결성 검증      : 성공")
print("====================================")