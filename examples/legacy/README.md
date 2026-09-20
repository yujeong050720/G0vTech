# 과거 실험 코드

현재 Flask 서버에서는 이 디렉터리를 사용하지 않습니다.
main.py/file_encryptor.py는 Fernet 데모, aes_encrypt.py는 AES-CBC 실험입니다.
aes_decrypt.py/test_all.py는 고정된 로컬 입력 파일을 필요로 하는 GCM 실험입니다.
서로 다른 암호화 형식이므로 하나의 실행 과정으로 연결하지 마세요.
이동 전 소스를 참고용으로 보존했으며, 기존 import/상대경로에 의존하므로 직접 실행용이 아닙니다.
현재 회귀 검증은 루트에서 `python -m unittest discover -s tests -v`로 실행합니다.
