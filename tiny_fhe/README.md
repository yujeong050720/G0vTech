# 기존 소형 모델 통합

지정된 kakao-private-ai 폴더의 tiny_fhe 모델과 파일 교환 경로를 가져왔습니다.
학습 코퍼스·가중치 계산·CKKS 계산은 그대로 유지합니다. 의존성은 함수 실행 시 로드합니다.
이는 제한된 합성 어휘로 다음 단어를 예측하는 실제 모델이며 의료 설명 모델은 아닙니다.

## 실행 (Python 3.12)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt -r tiny_fhe/requirements.txt
$env:LOCAL_API_TOKEN = .\.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:ENABLE_TINY_FHE_DEMO = '1'
# 필요하면 같은 셸에서 아래 요청 검증용으로 서버를 별도 실행합니다.
.\.venv\Scripts\python app.py
```

기존 `POST /medication-info`와 `prescription` JSON 필드는 유지합니다.
기본 MEDICATION_MODEL=tiny-fhe로 외부 API에 입력을 보내지 않습니다.
새 모델 경로와 medication-info에는 Authorization Bearer LOCAL_API_TOKEN이 필요합니다.
Origin이 있는 브라우저 요청은 기존 폴더의 정책대로 거부합니다.

```json
{"prescription":"음악 산책"}
```

처리: 문자열 검증 → 기존 모델의 어휘 검사 → CKKS 암호화 → 로컬 암호문 계산 → 복호화 및 오차 검증.
한 단어 입력은 기존 모델의 두 벡터 배치에 같은 단어를 넣고 결과 한 개만 반환합니다.
diagnosis는 호환을 위해 받지만 이 소형 모델의 입력으로 사용하지 않습니다.
결과 predictions에는 좋아해/즐겨가 나옵니다. explanation은 null이고 medical_llm은 false입니다.
약 이름처럼 어휘에 없는 입력은 422 MODEL_INPUT_UNSUPPORTED로 반환합니다.
알 수 없는 입력을 임의로 어휘에 대응시키거나 가짜 약 설명을 생성하지 않습니다.
로컬 직접 호출의 입력·키·결과는 임시 디렉터리에 만들고 처리가 끝나면 정리합니다.
키 보유 프로세스에서 로컬 검증하므로 원격 서버 분리 배포를 검증한 것은 아닙니다.

## 원래 파일 교환 방식도 유지

1. GET /private-ai/demo/capabilities: 어휘·활성화 여부.
2. POST /private-ai/demo/jobs: {"tokens":["음악","산책"]}.
3. 응답 request_url에서 공개 요청 ZIP 다운로드.
4. colab_server.ipynb에서 계산하거나 demo.py evaluate로 별도 계산.
5. POST /private-ai/demo/jobs/{job_id}/result에 multipart file로 결과 ZIP 전송.

파일 교환 작업의 비밀키는 local_data에 남으므로 PC 안에서 관리합니다.
원본 폴더의 비밀키·실제 입력·배포 인증 토큰은 복사하지 않았습니다.
현재 통합 범위는 tiny_fhe 모델·파일 교환 API·처방 입력 어댑터입니다.
범용 private_ai/Cloudflare 서버는 이 모델 실행에 필요하지 않아 복사하지 않았습니다.

## 호환성

이전 Claude 경로는 MEDICATION_MODEL=claude로 명시적으로 설정한 경우에만 사용합니다.
실패 시 자동으로 Claude/DUR 외부 API로 전환하지 않습니다.
기존 파일 업로드·SQLite 코드는 유지했습니다. 처방 API 응답은 모델 결과 스키마로 바뀝니다.
실제 약 설명 제공에는 이 소형 모델과 별도로 해당 기능을 수행하는 모델/자료 연결이 필요합니다.

## 테스트

```powershell
python -m unittest discover -s tests -v
```

test_model_bridge는 실제 TenSEAL이 필요하며 미설치 시 건너뛰어 성공으로 표시하지 않습니다.
