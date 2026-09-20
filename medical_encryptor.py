import json
import hashlib
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes


def encrypt_medical_data(medical_data):
    """
    의료데이터를 AES-256-GCM으로 암호화하고
    SHA-256 HASH를 생성한다.

    반환값:
        encrypted_data : 암호화된 의료데이터
        aes_key        : AES-256 암호화 키
        file_hash      : 암호화된 데이터의 SHA-256 HASH
    """

    # 1. 의료데이터 JSON → bytes
    data = json.dumps(
        medical_data,
        ensure_ascii=False,
        separators=(",", ":")
    ).encode("utf-8")

    # 2. AES-256 Key 생성
    # 데이터마다 새로운 32바이트 키 생성
    aes_key = get_random_bytes(32)

    # 3. AES-256-GCM 암호화
    cipher = AES.new(aes_key, AES.MODE_GCM)

    ciphertext, tag = cipher.encrypt_and_digest(data)

    # 4. nonce + tag + ciphertext
    encrypted_data = (
        cipher.nonce +
        tag +
        ciphertext
    )

    # 5. 암호화된 데이터의 SHA-256 HASH 생성
    file_hash = hashlib.sha256(
        encrypted_data
    ).hexdigest()

    return encrypted_data, aes_key, file_hash


if __name__ == "__main__":

    # 테스트용 의료데이터 불러오기
    with open(
        "sample_medical_data.json",
        "r",
        encoding="utf-8"
    ) as f:
        medical_data = json.load(f)

    # 암호화
    encrypted_data, aes_key, file_hash = encrypt_medical_data(
        medical_data
    )

    # 암호화 파일 저장
    with open("encrypted.bin", "wb") as f:
        f.write(encrypted_data)

    # 테스트용 AES Key 저장
    # 실제 서비스에서는 평문 AES Key를 파일로 저장하지 않음
    with open("aes_key.bin", "wb") as f:
        f.write(aes_key)

    # HASH 저장
    with open("hash.txt", "w", encoding="utf-8") as f:
        f.write(file_hash)

    print("의료데이터 암호화 완료")
    print(f"AES Key 길이: {len(aes_key)} bytes")
    print(f"SHA-256: {file_hash}")