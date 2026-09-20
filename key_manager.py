from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Hash import SHA256


def generate_hospital_keys():
    """
    병원용 RSA-3072 공개키/개인키를 생성한다.
    """

    # RSA-3072 키 생성
    key = RSA.generate(3072)

    # 병원 개인키
    with open("hospital_private.pem", "wb") as f:
        f.write(
            key.export_key(
                format="PEM",
                pkcs=8
            )
        )

    # 병원 공개키
    with open("hospital_public.pem", "wb") as f:
        f.write(
            key.publickey().export_key()
        )

    print("병원 RSA-3072 키 생성 완료")


def encrypt_aes_key(aes_key, output_file="encrypted_key.bin"):
    """
    AES 키를 병원 공개키로 RSA-OAEP 암호화한다.

    매개변수:
        aes_key      : AES-256 키
        output_file  : 암호화된 AES 키를 저장할 파일

    반환값:
        encrypted_key : RSA로 암호화된 AES 키
    """

    # 병원 공개키 불러오기
    with open("hospital_public.pem", "rb") as f:
        public_key = RSA.import_key(f.read())

    # RSA-OAEP + SHA-256
    cipher = PKCS1_OAEP.new(
        public_key,
        hashAlgo=SHA256
    )

    # AES Key 암호화
    encrypted_key = cipher.encrypt(aes_key)

    # 암호화된 AES Key 저장
    with open(output_file, "wb") as f:
        f.write(encrypted_key)

    return encrypted_key


def decrypt_aes_key(encrypted_key):
    """
    RSA로 암호화된 AES 키를 병원 개인키로 복호화한다.

    매개변수:
        encrypted_key : RSA로 암호화된 AES 키

    반환값:
        aes_key : 복호화된 AES-256 키
    """

    # 병원 개인키 불러오기
    with open("hospital_private.pem", "rb") as f:
        private_key = RSA.import_key(f.read())

    # RSA-OAEP + SHA-256
    cipher = PKCS1_OAEP.new(
        private_key,
        hashAlgo=SHA256
    )

    # 암호화된 AES Key 복호화
    aes_key = cipher.decrypt(encrypted_key)

    return aes_key