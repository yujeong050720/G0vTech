# 테스트

프로젝트 루트에서 의존성을 설치한 뒤 실행합니다.

```powershell
.\.venv\Scripts\python -m pip install -r requirements.txt -r tiny_fhe/requirements.txt
.\.venv\Scripts\python -m unittest discover -s tests -v
```

로컬 검증에서 총 34개 테스트가 통과했습니다.

- AES/RSA 암호화와 변조 거부
- 실제 CKKS 계산·복호화 및 수치 검증
- 처방 입력, 인증, 기록 저장과 오류 처리
- 웹 요청 제한, 비공개 결과 필드 보호, 중단된 작업 처리
- 웹 흐름의 메인넷 거래 차단과 암호화 키 메타데이터 보존

외부 IPFS·블록체인·Supabase 호출은 모의 처리합니다. 테스트 통과만으로 실제 외부 서비스 연결까지 성공했다고 볼 수는 없습니다. 실제 연결은 CLI 또는 웹에서 별도로 검증하세요.
