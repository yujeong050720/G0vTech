# 무료 클라우드 웹 데모 배포

기존 로컬 CLI는 그대로 유지합니다. 공개용 진입점은 **web_demo.py**입니다. `app.py` 전체를 공개하지 않습니다.

## 비용과 범위

- Render **Free Web Service** 한 개 + Supabase **Free** 프로젝트 + 기존 Pinata Free + Sepolia.
- PC를 꺼도 서버는 Render에서 실행됩니다. 15분간 요청이 없으면 잠들며 첫 접속 시 약 1분 이상 기다릴 수 있습니다.
- Render 무료 서버의 디스크는 재시작 시 사라집니다. 기록과 RSA로 감싼 AES 키는 Supabase, 암호화 파일은 실제 IPFS, CID는 실제 Sepolia에 저장합니다.
- 결제 수단을 추가하지 않고 Free를 선택하세요. 한도 초과 시 중단되는 방식으로 사용합니다. 유료 업그레이드/자동 결제를 활성화하지 않습니다. 가입 과정에서 카드나 결제가 필수라면 중단하세요.
- 무료 정책은 변경될 수 있고 상시 가동이나 영구 보존을 보장하지 않습니다. Supabase Free도 비활성 시 일시 정지될 수 있습니다.
- 가상 처방 두 문장만 허용하며 공유 체험 코드가 필요합니다. SQL에서 하루 UTC 기준 총 20회, 서버에서 한 번에 1명으로 제한합니다.
- 서버가 브라우저 입력을 받습니다. CKKS 암호화는 서버에서 AI 평가 프로세스로 넘기기 전에 수행됩니다. 브라우저부터의 동형암호화나 범용 LLM은 아닙니다.

공식 조건: [Render Free](https://render.com/docs/free), [Supabase Free](https://supabase.com/pricing).

## 1. 로컬 화면 확인

Python 3.12 가상환경에서:

```powershell
python -m pip install -r requirements-web.txt
python web_demo.py
```

http://127.0.0.1:7860/ 에서 화면을 볼 수 있습니다. 키와 클라우드 DB가 설정되지 않으면 안내 배너를 표시하고 실험 요청은 거부합니다. 가짜 성공 결과를 반환하지 않습니다.

## 2. Supabase Free 프로젝트 준비

1. https://supabase.com 에서 가입하고 **Free** 조직에 새 프로젝트를 만듭니다.
2. 프로젝트의 SQL Editor에서 `deploy/supabase.sql` 전체를 실행합니다.
3. 프로젝트 URL과 **Secret API key (`sb_secret_...`)**를 보관합니다. anon/publishable 키는 사용하지 않습니다.
4. 테이블은 RLS를 켜고 일반 방문자 권한을 제거합니다. 이 키는 Render 환경변수에만 넣습니다.

Supabase는 IPFS·원장을 대체하지 않고 요청 상태와 암호화 키 연결을 보관합니다.

## 3. 파일 복호화용 RSA 키 준비

프로젝트 루트에서:

```powershell
python deploy/create_public_key.py
```

출력된 `HOSPITAL_PUBLIC_KEY_B64` 값만 Render에 넣습니다. `local_data/web-owner-private.pem`은 별도 안전한 곳에 백업하고 GitHub/Render/채팅에 올리지 않습니다. 기존 로컬 실험 키를 덮어쓰지 않으며, 새 웹 실험용 키를 만듭니다.

같은 폴더에서 재실행하면 기존 키를 유지합니다. 최초 배포 후 키를 변경하면 이전 IPFS 파일 복호화에는 이전 개인키가 필요합니다. 자동 복호화 UI는 아직 없습니다.

## 4. Render Free 서버 생성

이 웹 버전의 파일이 포함된 GitHub 저장소를 준비한 뒤 https://dashboard.render.com 에 로그인합니다.

### Blueprint 사용

1. New → Blueprint에서 GitHub 저장소를 연결합니다.
2. `render.yaml`이 인식되는지 확인합니다.
3. Web Service의 **plan: free**를 확인합니다. 데이터베이스 등 유료 리소스는 이 파일에 없습니다.
4. 아래 환경변수를 설정하고 배포합니다.

### 수동 생성 시

New → Web Service → Python → **Free**를 선택합니다.

```text
Build Command: pip install -r requirements-web.txt
Start Command: python web_demo.py
Health Check Path: /health
PYTHON_VERSION: 3.12.8
HOST: 0.0.0.0
OPENBLAS_NUM_THREADS: 1
OMP_NUM_THREADS: 1
```

Render가 제공하는 PORT 환경변수를 자동으로 사용합니다. 서버 프로세스는 하나만 실행하세요.

### 서버 환경변수

| 이름 | 값 |
| --- | --- |
| PINATA_JWT | **V3 Files → Write** 권한의 JWT |
| WEB3_PROVIDER_URL | Sepolia HTTPS RPC |
| CONTRACT_ADDRESS | `0xcC8AA93b0E3b8FA50688D0e36CD15281424a201B` 또는 본인의 Sepolia 배포 주소 |
| PRIVATE_KEY | Sepolia 테스트 ETH가 있는 테스트 전용 지갑 개인키 |
| SUPABASE_URL | `https://프로젝트ID.supabase.co` |
| SUPABASE_SECRET_KEY | Supabase Secret 키 (`sb_secret_...`) |
| HOSPITAL_PUBLIC_KEY_B64 | 3단계에서 출력된 RSA 공개키 |
| DEMO_ACCESS_CODE | 방문자에게 전달할 16자 이상 무작위 체험 코드 |

체험 코드는 다음 명령으로 만들 수 있습니다. 출력된 코드만 방문자와 공유합니다.

```powershell
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

`.env` 자동 로딩은 없습니다. 비밀 값은 GitHub 파일이나 HTML에 쓰지 않습니다.

## 5. 공유 및 전체 검증

1. 배포 후 Render가 제공하는 `https://서비스명.onrender.com`을 엽니다.
2. 체험 코드 입력 → 가상약A 또는 가상약B 선택 → 전체 과정 실험하기.
3. IPFS 업로드, Sepolia 등록, AI 계산의 결과를 확인합니다.
4. `REGISTERED`, `SUCCEEDED`, `verified: true`가 전체 성공 조건입니다.
5. 결과 JSON을 저장하고 거래 링크에서 Sepolia 영수증을 확인합니다.
6. 재시작 후에는 같은 탭의 '최근 실험 결과 다시 확인'으로 Supabase의 결과를 읽을 수 있습니다. 진행 중 재시작되면 `INTERRUPTED`로 표시하며 자동 재전송하지 않습니다.

Render의 느린 CPU에서 계산 또는 거래 확인에 몇 분 걸릴 수 있습니다. 시간 초과 시 새 요청을 반복하지 말고 최근 결과와 거래 해시를 확인하세요. 운영자와 방문자는 개인키나 JWT 대신 **웹 주소와 체험 코드만** 공유합니다.

## 검증 현황

- Windows/Python 3.12에서 기존 29개 + 웹 데모 5개 테스트 통과.
- 별도 프로세스로 분리한 실제 CKKS 생성/평가/복호화 검증 통과.
- 서버 모듈과 모델 자식 프로세스의 합산 RSS 최고값 약 357 MiB 측정. Linux/Render의 실제 사용량과 시간은 다를 수 있으므로 최초 배포 후 확인이 필요합니다.
- 자동 테스트는 Supabase/IPFS/블록체인 외부 호출을 mock으로 처리합니다. 새 Render/Supabase 계정에서의 배포와 실제 통합 호출은 아직 완료하지 않았습니다.
- 로컬 모델의 기존 전체 실행 성공과 공개 클라우드의 배포 성공을 구분합니다.
