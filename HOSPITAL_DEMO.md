# 병원 처방전 + 기존 IPFS/블록체인 + 동형암호 AI

로컬 저장 대체 모드를 제거했습니다. 기존 upload_file_to_pinata()와 register_file_on_chain()을 반드시 호출합니다.
SQLite는 처리 상태·환자와 파일의 연결을 관리하는 메타데이터 저장소이며 IPFS/원장을 대체하지 않습니다.
기존 HOSPITAL_STORAGE_BACKEND 값은 더 이상 사용하지 않습니다.

## 흐름

처방전 JSON 한 번 업로드:
1. 전체 JSON을 AES-GCM 암호화하고 AES 키를 RSA로 보호합니다.
2. 기존 Pinata 함수로 암호화 파일을 IPFS에 업로드합니다.
3. 기존 블록체인 함수로 CID와 무작위 기록 ID를 FileRegistry에 등록합니다.
4. 환자별 기록과 CID·거래 해시를 병원 측 메타데이터에 연결합니다.
5. 처방 문장만 CKKS로 암호화해 별도 프로세스의 기존 초소형 문장 모델에 전달합니다.
6. 암호문 답변 점수를 사용자/병원 측에서 복호화해 전체 안내문을 반환합니다.

원장에는 의료 원문이나 환자 식별자를 올리지 않습니다. 모델과 학습 규모는 유지했습니다.
AI는 저장 결과와 별도로 처리합니다. 저장 실패는 FAILED, 거래 확인 대기는 CHAIN_PENDING이며
IPFS/블록체인 실패를 로컬 저장 성공으로 바꾸지 않습니다. 자동 재전송은 없습니다.

## 실행

기존 PINATA_JWT, WEB3_PROVIDER_URL, CONTRACT_ADDRESS, PRIVATE_KEY를 실행 셸에 설정하세요.
.env 자동 로딩은 없습니다. 실행하면 실제 IPFS 업로드와 트랜잭션 전송이 발생합니다.

```powershell
..\.venv312\Scripts\python hospital_demo.py
```

파일 업로드:

```powershell
..\.venv312\Scripts\python hospital_demo.py --file examples/prescription.synthetic.json
```

입력 예: 가상약A 1정 처방 / 가상약B 1정 처방.
처방 JSON: {"patient_ref":"demo-patient-001","prescription":"가상약A 1정 처방"}

## 기존 서버

변경 반영을 위해 서버를 Ctrl+C 후 다시 실행하세요.
POST /hospital/prescriptions의 multipart file로 JSON을 보냅니다.
GET /hospital/patients/{patient_ref}/records로 기록을 조회합니다.
두 경로 모두 기존 LOCAL_API_TOKEN 인증을 사용합니다.
전체 성공 201, 저장/AI 부분 실패 207이며 storage와 ai를 각각 확인하세요.

local_data/hospital의 RSA 키와 기록 연결 정보는 보존해야 합니다.
개인 키를 잃으면 IPFS 파일이 있어도 복호화할 수 없습니다.
기존 /upload API의 저장 흐름 역시 유지합니다.

## 검증 범위

실제 AES/RSA·CKKS 계산, 환자 기록 및 실패 처리를 테스트했습니다.
테스트에서만 외부 IPFS/블록체인 호출을 mock으로 대체합니다.
실제 Pinata/블록체인 연결 성공 여부는 환경변수와 배포된 컨트랙트로 별도 확인해야 합니다.
가상 약물 문장은 의료 안내가 아니며, 모델은 범용 LLM이 아닌 작은 조건부 토큰 모델입니다.
