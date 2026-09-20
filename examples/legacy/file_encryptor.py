from cryptography.fernet import Fernet
import os

# 1. 암호화 키 생성 및 저장 함수
def generate_key(key_path="secret.key"):
    """새로운 대칭키를 생성하고 파일로 저장합니다."""
    key = Fernet.generate_key()
    with open(key_path, "wb") as key_file:
        key_file.write(key)
    print(f"🔑 새로운 암호화 키가 생성되었습니다: '{key_path}'")
    print("🚨 주의: 이 키를 잃어버리면 파일을 영영 복구할 수 없으며, 유출되면 누구나 파일을 열어볼 수 있습니다!")
    return key

# 2. 저장된 키 불러오기 함수
def load_key(key_path="secret.key"):
    """저장된 키 파일을 읽어옵니다."""
    return open(key_path, "rb").read()

# 3. 파일 암호화 함수
def encrypt_file(file_path, key):
    """파일을 읽어 암호화한 뒤, 새로운 확장자(.encrypted)로 저장합니다."""
    f = Fernet(key)

    # 원본 파일이 있는지 확인
    if not os.path.exists(file_path):
        print(f"❌ 오류: '{file_path}' 파일을 찾을 수 없습니다.")
        return None

    # 원본 데이터 읽기
    with open(file_path, "rb") as file:
        file_data = file.read()

    # 데이터 암호화 진행
    encrypted_data = f.encrypt(file_data)

    # 암호화된 파일 저장
    encrypted_file_path = file_path + ".encrypted"
    with open(encrypted_file_path, "wb") as file:
        file.write(encrypted_data)

    print(f"🔒 파일 암호화 완료! 생성된 파일: '{encrypted_file_path}'")
    return encrypted_file_path

# --- 테스트 실행 부분 ---
if __name__ == "__main__":
    # 테스트용 기밀(?) 파일 생성
    test_file = "secret_document.txt"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("이 문서는 극비 문서입니다. 암호화가 반드시 필요합니다.")

    # 1. 키 생성 (최초 1회만 실행하고, 이후에는 주석 처리 후 load_key를 사용하세요)
    my_key = generate_key()
    
    # 만약 이미 키를 만들었다면 위 코드를 주석(#) 처리하고 아래 코드를 쓰세요.
    # my_key = load_key()

    # 2. 파일 암호화 실행
    encrypted_path = encrypt_file(test_file, my_key)