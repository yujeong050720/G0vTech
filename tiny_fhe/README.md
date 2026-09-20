# 동형암호 문장 모델

현재 서비스는 `sentence_model.py`의 초소형 조건부 토큰 모델을 사용합니다. 두 가지 가상 처방 문장으로 학습하며, 입력을 CKKS로 암호화한 상태에서 모델 점수를 계산합니다.

| 입력 | 출력 |
| --- | --- |
| 가상약A 1정 처방 | 실험용 문구입니다 음주를 피하세요 |
| 가상약B 1정 처방 | 실험용 문구입니다 식사 시간을 확인하세요 |

지원하는 문장만 입력할 수 있습니다. 범용 LLM이나 실제 의료 모델은 아닙니다.

## 설치와 실행

프로젝트 루트에서 Python 3.12로 실행합니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt -r tiny_fhe/requirements.txt
.\.venv\Scripts\python -m tiny_fhe.sentence_model
```

학습 입력과 답변은 `sentence_model.py`의 `TRAINING_PAIRS`에 있습니다.

## 계산 과정

1. 입력 문장을 단어 빈도 벡터로 변환합니다.
2. 답변 위치별 토큰을 예측하는 선형 가중치를 학습합니다.
3. 입력 벡터를 CKKS로 암호화합니다.
4. 별도 평가 프로세스에서 암호문 행렬 연산을 수행합니다.
5. 결과 점수를 복호화하고 위치별 argmax로 답변 토큰을 선택합니다.

`verified`는 평문 기준 계산과 암호문 계산 결과의 수치 검증입니다. 의료적 정확성이나 악성 서버에 대한 암호학적 증명을 뜻하지 않습니다.

## 로컬 API

`app.py`의 `/medication-info` 기본 모델은 `sentence-fhe`입니다.

```powershell
$env:LOCAL_API_TOKEN = (& .\.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(32))")
$env:MEDICATION_MODEL = 'sentence-fhe'
.\.venv\Scripts\python app.py
```

`POST /medication-info`에 다음 JSON과 `Authorization: Bearer <LOCAL_API_TOKEN>` 헤더를 보냅니다.

```json
{"prescription":"가상약A 1정 처방"}
```

안내 문장은 응답의 `explanation`에 있습니다. 이 로컬 API는 Origin 헤더가 있는 브라우저 요청을 거부합니다. 공개 웹 UI는 별도 진입점인 `web_demo.py`를 사용합니다.

## 기존 실험 코드

`demo.py`, `prescription.py`, `routes.py`, Colab 파일은 이전 다음 단어 예측·문장 조회·파일 교환 실험용입니다. 현재 문장 모델과 구분해야 합니다.

`MEDICATION_MODEL=tiny-fhe`는 이전 경로를 선택합니다. 이 경로에는 등록 문장을 그대로 조회하는 처리도 있으므로 모든 응답이 동형암호 모델의 생성 결과인 것은 아닙니다.

## 검증

프로젝트 루트에서 실행합니다.

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
```

자세한 계산 구조는 [SENTENCE_DEMO.md](SENTENCE_DEMO.md)를 참고하세요.
