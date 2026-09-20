# kakao-project — 로컬 통합 실험

가상 처방전 JSON을 암호화하여 실제 IPFS에 업로드하고, 암호화 파일의 CID를 Sepolia 블록체인에 등록합니다. 처방 문장은 CKKS 동형암호로 암호화하여 작은 학습 모델에서 계산한 뒤, 로컬에서 결과를 복호화합니다.

**로컬 실행과 웹 체험 버전**을 포함합니다. 무료 클라우드 배포 방법은 [WEB_DEPLOY.md](WEB_DEPLOY.md)를 참고하세요. 웹 진입점은 `web_demo.py`, 기존 로컬 API는 `app.py`입니다. AI는 서버의 별도 프로세스에서 실행됩니다. 모델은 두 가지 가상 처방 문장을 학습한 조건부 토큰 모델이며 범용 LLM 또는 실제 의료용 모델이 아닙니다.

## 처리 흐름

```text
가상 처방전 JSON
├─ AES-GCM 암호화 + AES 키의 RSA 보호
│  → 실제 Pinata IPFS 업로드 → CID를 실제 Sepolia FileRegistry에 등록
│  → 로컬 SQLite에 환자별 기록 연결 및 처리 상태 저장
└─ 처방 문장 → 로컬 CKKS 암호화 → 별도 프로세스에서 암호문 행렬 연산
   → 로컬 복호화 및 토큰 선택 → 안내 문장 출력
```

원장에는 의료 원문이나 환자 식별자 대신 CID와 무작위 기록 ID를 올립니다. SQLite는 메타데이터를 관리하며 IPFS나 블록체인을 대체하지 않습니다. 저장과 AI 결과는 각각 확인해야 합니다.

## 1. 설치 — Windows PowerShell

Python **3.12 (64비트)**와 Git을 준비하세요. 아래 명령은 프로젝트 루트에서 실행합니다.

```powershell
git clone https://github.com/yujeong050720/medical-blockchain-demo.git
cd medical-blockchain-demo
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt -r tiny_fhe/requirements.txt
```

이 README가 포함된 최신 코드를 사용하세요. ZIP으로 내려받았다면 압축을 풀고 `app.py`, `requirements.txt`가 있는 폴더로 이동한 뒤 가상환경 생성부터 진행하면 됩니다.

Python 3.14용 `requirements-lock.txt`는 이 모델의 설치에 사용하지 않습니다. TenSEAL 설치 시 호환 버전 오류가 나면 `.\.venv\Scripts\python --version`이 Python 3.12인지 먼저 확인하세요.

## 2. 계정·키 없이 전체 자동 테스트

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
```

검증 시 29개 테스트가 모두 통과했습니다. 마지막에 `OK`가 나오면 성공입니다.

- 실제 AES/RSA 암호화, 변조 거부, 실제 CKKS 모델 연산과 복호화를 검증합니다.
- 환자 기록, 인증, 업로드 성공·실패, 거래 확인 대기 및 실패 처리를 검증합니다.
- **자동 테스트에서 외부 IPFS·블록체인 호출은 mock으로 대체합니다.** 실제 업로드·거래 성공은 다음 단계에서 별도로 확인합니다.

모델만 직접 실행하려면:

```powershell
.\.venv\Scripts\python -m tiny_fhe.sentence_model
```

입력 예: `가상약A 1정 처방` 또는 `가상약B 1정 처방`.

## 3. 실제 IPFS·Sepolia 연결 준비

각 실행자는 자신의 인증 정보를 준비합니다. 본 실험에는 실제 ETH 구매가 필요하지 않습니다. Sepolia faucet에서 받은 테스트 ETH로 거래 수수료를 지불하고, 외부 서비스는 무료 플랜 한도 안에서 사용하세요.

| 환경변수 | 준비할 값 |
| --- | --- |
| `PINATA_JWT` | Pinata API Keys에서 만든 JWT. **V3 RESOURCES → Files → Write** 권한 필요 |
| `WEB3_PROVIDER_URL` | Alchemy 등의 **Ethereum Sepolia HTTPS RPC** 주소 |
| `CONTRACT_ADDRESS` | Sepolia에 배포된 `FileRegistry` 주소 |
| `PRIVATE_KEY` | 테스트 ETH를 받은 본인 Ethereum/EVM 계정의 개인키 |

- Pinata의 **API Key/API Secret과 JWT는 다릅니다.** 현재 코드는 V3 업로드 API를 사용하므로 Legacy `pinFileToIPFS` 권한만으로는 부족합니다.
- RPC 예시: `https://eth-sepolia.g.alchemy.com/v2/본인의_API키`.
- 개인키는 12·24개 단어로 된 지갑 복구 문구가 아닙니다.
- 직접 배포하려면 `contracts/FileRegistry.sol`을 Remix에서 컴파일한 뒤, 지갑을 **Sepolia (11155111)**에 연결하고 Value `0`으로 배포하세요.
- 아래 실험용 공개 컨트랙트도 사용할 수 있습니다. 호출자의 지갑 주소별로 기록이 저장됩니다.

```text
0xcC8AA93b0E3b8FA50688D0e36CD15281424a201B
```

### 환경변수 설정

아래 명령을 **하나씩** 실행합니다. `Read-Host` 안내가 나타난 뒤 실제 값을 붙여넣고 Enter를 누르세요. 따옴표나 `Bearer`는 붙이지 않습니다.

```powershell
$env:PINATA_JWT = [System.Net.NetworkCredential]::new('', (Read-Host "Pinata JWT 입력" -AsSecureString)).Password.Trim()
$env:WEB3_PROVIDER_URL = [System.Net.NetworkCredential]::new('', (Read-Host "Sepolia HTTPS RPC 주소 입력" -AsSecureString)).Password.Trim()
$env:CONTRACT_ADDRESS = "0xcC8AA93b0E3b8FA50688D0e36CD15281424a201B"
$env:PRIVATE_KEY = [System.Net.NetworkCredential]::new('', (Read-Host "테스트 지갑 개인키 입력" -AsSecureString)).Password.Trim()
```

입력값은 화면에 표시되지 않습니다. 이후 명령도 **같은 PowerShell 창**에서 실행하세요. 창을 닫으면 다시 설정해야 합니다. `.env` 파일은 자동으로 읽지 않습니다.

### RPC·컨트랙트 연결 확인

```powershell
.\.venv\Scripts\python -c "import os; from web3 import Web3; w=Web3(Web3.HTTPProvider(os.environ['WEB3_PROVIDER_URL'])); print('연결:', w.is_connected()); print('체인 ID:', w.eth.chain_id); print('컨트랙트 코드 길이:', len(w.eth.get_code(Web3.to_checksum_address(os.environ['CONTRACT_ADDRESS']))))"
```

성공 기준: 연결 `True`, 체인 ID `11155111`, 컨트랙트 코드 길이 `0`보다 큼.

## 4. 실제 전체 과정 실행

서버를 따로 켤 필요 없이 다음 명령을 실행합니다.

```powershell
.\.venv\Scripts\python hospital_demo.py --file examples/prescription.synthetic.json
```

예제 파일의 입력:

```json
{"patient_ref":"demo-patient-001","prescription":"가상약A 1정 처방"}
```

직접 입력하려면:

```powershell
.\.venv\Scripts\python hospital_demo.py
```

현재 모델에서 지원하는 입력과 출력:

| 입력 | 출력 |
| --- | --- |
| `가상약A 1정 처방` | `실험용 문구입니다 음주를 피하세요` |
| `가상약B 1정 처방` | `실험용 문구입니다 식사 시간을 확인하세요` |

그 외 문장은 지원하지 않습니다. 학습 예제는 `tiny_fhe/sentence_model.py`의 `TRAINING_PAIRS`에 있습니다.

### 전체 성공 기준

| 출력 항목 | 성공 값 |
| --- | --- |
| `storage.status` | `REGISTERED` |
| `storage.cid` | IPFS CID 존재 |
| `storage.tx_hash` | Sepolia 거래 해시 존재 |
| `ai.status` | `SUCCEEDED` |
| `ai.verified` | `true` |
| `ai.explanation` | 해당 입력의 안내 문장 |

`verified`는 복호화한 모델 점수와 평문 기준 계산의 수치 검증 결과이며, 의료적 정확성을 뜻하지 않습니다.

**명령이 종료됐거나 환자 기록 개수가 증가했다는 것만으로 전체 성공은 아닙니다.** 기록 개수에는 실패한 요청도 포함됩니다. `storage.status`가 `FAILED`이면 `failed_stage`를 확인하고, `CHAIN_PENDING`이면 거래 해시로 영수증을 확인하세요. AI는 저장 실패와 별개로 성공할 수 있습니다.

실행할 때마다 새 기록이 만들어지며 실제 IPFS 업로드와 Sepolia 거래를 시도합니다. 반복 실행은 동일 기록을 재개하는 기능이 아닙니다.

### 실제 성공 사례

사용자 로컬 실행 결과에서 실제 IPFS 업로드, Sepolia `REGISTERED`, AI `SUCCEEDED` 및 `verified: true`가 확인되었습니다.

- 입력: `가상약A 1정 처방`
- 출력: `실험용 문구입니다 음주를 피하세요`
- CID: `bafkreiagcgri2za2qmju4msx32737drnhaxbybcomltakm7g4n55a4yyby`
- [Sepolia 등록 거래 확인](https://sepolia.etherscan.io/tx/0xf0fa36f163ec640e8075d43cd0dec2ecf30a06ad2450fe5fe820a01184112c16)

거래 링크는 원장 등록의 증거입니다. AI 동작은 자동 테스트와 로컬 실행 결과로 별도 확인합니다.

## 5. API 서버 실행 — 선택 사항

같은 창에서 외부 연결 환경변수를 설정한 뒤 실행합니다.

```powershell
$env:LOCAL_API_TOKEN = (& .\.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(32))")
.\.venv\Scripts\python app.py
```

- 주소: http://127.0.0.1:5000/
- 루트의 `Server is running.` 응답은 정상이며 입력 UI는 없습니다.
- 종료: `Ctrl+C`
- `POST /hospital/prescriptions`: multipart의 `file` 필드로 처방전 JSON 업로드
- `GET /hospital/patients/{patient_ref}/records`: 환자 기록 조회
- 두 경로에 `Authorization: Bearer <LOCAL_API_TOKEN>` 헤더가 필요합니다.
- 병원 업로드 API의 전체 성공은 HTTP `201`, 부분 실패는 `207`입니다. 응답의 `storage`와 `ai`를 함께 확인하세요.

## 문제 해결

| 증상 | 확인 사항 |
| --- | --- |
| Pinata `401` | JWT 전체를 입력했는지, **V3 Files → Write** 권한이 있는지 확인 후 다시 설정 |
| RPC 연결 실패 | Sepolia HTTPS 주소와 API 키 확인 |
| 체인 ID가 `1` | 메인넷 주소입니다. Sepolia RPC로 변경 |
| 컨트랙트 코드 길이가 `0` | RPC 네트워크와 배포 주소가 일치하는지 확인 |
| 거래 잔액 부족 | `PRIVATE_KEY`에 해당하는 지갑의 **Sepolia ETH** 잔액 확인 |
| `UNSUPPORTED_INPUT` | 위 지원 문장을 그대로 입력 |
| `requirements.txt` 또는 `app.py` 없음 | 프로젝트 루트 폴더로 이동 |

## GitHub 업로드 및 로컬 데이터

코드, 테스트, 가상 처방전 예제와 문서를 공유하세요. JWT, RPC API 키, 지갑 개인키, 복구 문구, 실제 환자 데이터는 올리지 않습니다.

다음 항목은 업로드 대상에서 제외해야 합니다.

```text
.env 및 비밀 설정 파일
.venv*/
local_data/
keys/
개인키·복호화 키 파일
실제 환자 데이터와 실행 로그
```

업로드 전 `git status --short`와 `git diff --cached`로 포함 파일과 내용을 확인하세요. `.gitignore`는 이미 추적 중인 파일을 자동으로 제외하지 않습니다.

`local_data/hospital`에는 RSA 키와 환자 기록 연결 정보가 있으므로 **GitHub에 올리지 않되 로컬에서는 보존**하세요. 키를 잃으면 IPFS 파일이 있어도 복호화할 수 없습니다.

## 범위와 제한

- 동형암호 모델은 같은 PC의 별도 프로세스에서 암호문 행렬 연산을 수행합니다. 복호화와 출력 토큰 선택은 로컬 클라이언트에서 합니다.
- 고정된 가상 처방 실험이며 실제 진료나 복약 안내에 사용하지 않습니다. DUR/Anthropic 키는 이 실험에 필요하지 않습니다.
- 웹 버전은 가상 처방 전용 공유 코드 체험입니다. 병원·환자별 접근 권한, 다운로드·복호화 API 및 다중 프로세스 거래 조정은 별도 구현이 필요합니다.
- 단일 요청 흐름으로 실행하세요. 대기·중단 작업의 자동 재개나 거래 재전송 기능은 없습니다.

추가 설명: [병원 통합 실험](HOSPITAL_DEMO.md), [문장 모델](tiny_fhe/SENTENCE_DEMO.md).
