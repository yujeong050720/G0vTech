from flask import Flask, request, jsonify
import os
import json
from uuid import uuid4
from werkzeug.utils import secure_filename

from medical_encryptor import encrypt_medical_data
from key_manager import generate_hospital_keys, encrypt_aes_key
from IPFS_upload import upload_file_to_pinata
from blockchain_registry import register_file_on_chain, ChainPending
from registry_store import RegistryStore
from ai_advisor import (
    fetch_dur_taboo_info,
    generate_medication_explanation,
    build_health_stats,
    generate_health_report,
)

app = Flask(__name__)
from tiny_fhe.routes import bp as tiny_fhe_blueprint
from tiny_fhe.prescription import authorize as authorize_model, predict as predict_prescription
app.register_blueprint(tiny_fhe_blueprint)
from hospital_service import bp as hospital_blueprint
app.register_blueprint(hospital_blueprint)


@app.before_request
def protect_local_model():
    if request.path == '/medication-info' or request.path.startswith('/private-ai/demo/'):
        return authorize_model()


@app.after_request
def model_response_headers(response):
    if request.path == '/medication-info' or request.path.startswith('/private-ai/demo/'):
        response.headers['Cache-Control'] = 'no-store'
    return response

# ---------------------------------------------------------
# 기본 설정
# ---------------------------------------------------------
UPLOAD_FOLDER = 'uploads'          # 원본(평문 JSON) 임시 저장소 - 처리 후 즉시 삭제
ENCRYPTED_FOLDER = 'encrypted'     # AES-256-GCM으로 암호화된 의료데이터 저장소
KEYS_FOLDER = 'keys'                # 파일별 RSA 암호화된 AES 키 저장소 (평문 키는 저장 안 함)
app.config['REGISTRY_DATABASE'] = os.environ.get('REGISTRY_DATABASE', 'registry.sqlite3')

# key_manager.py가 고정 경로로 사용하는 병원 RSA 키 파일 (현재 병원 구분 없이 전역 1개)
HOSPITAL_PUBLIC_KEY_PATH = 'hospital_public.pem'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 업로드 최대 16MB 제한

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(ENCRYPTED_FOLDER, exist_ok=True)
os.makedirs(KEYS_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'json'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def ensure_hospital_keys():
    """
    key_manager.py는 hospital_public.pem / hospital_private.pem을
    현재 작업 디렉토리에 고정된 파일명으로 읽고 쓴다 (병원별 분리는 아직 미지원).
    없으면 최초 1회 생성한다.
    """
    if not os.path.exists(HOSPITAL_PUBLIC_KEY_PATH):
        generate_hospital_keys()


def get_registry():
    return RegistryStore(app.config['REGISTRY_DATABASE'])


# ---------------------------------------------------------
# 헬스체크
# ---------------------------------------------------------
@app.route('/')
def index():
    return jsonify({"message": "Server is running."})


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})


# ---------------------------------------------------------
# 의료데이터 업로드:
# JSON 파싱 -> AES-256-GCM 암호화 -> AES키 RSA 암호화
# -> IPFS 업로드 -> 블록체인 등록
# ---------------------------------------------------------
@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    if file is None or not file.filename:
        return jsonify({"error": "JSON 파일이 필요합니다."}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "JSON 파일만 업로드 가능합니다."}), 400

    file_id = str(uuid4())
    filename = file_id + '.json'
    plain_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    store = get_registry()
    store.create(file_id, filename=filename,
                 original_filename=secure_filename(file.filename), status='RECEIVED')
    stage = 'VALIDATION'
    aes_key = None
    try:
        file.save(plain_path)
        try:
            with open(plain_path, encoding='utf-8') as source:
                medical_data = json.load(source)
            if not isinstance(medical_data, dict):
                raise ValueError('의료 JSON은 객체여야 합니다.')
        except (ValueError, UnicodeDecodeError):
            store.update(file_id, status='FAILED', failed_stage=stage, error='INVALID_JSON')
            return jsonify({"id": file_id, "error": "올바른 JSON 객체가 필요합니다."}), 400

        stage = 'ENCRYPTION'
        ensure_hospital_keys()
        encrypted_data, aes_key, file_hash = encrypt_medical_data(medical_data)
        encrypted_path = os.path.join(ENCRYPTED_FOLDER, filename + '.encrypted')
        with open(encrypted_path, 'wb') as output:
            output.write(encrypted_data)
        encrypted_key_path = os.path.join(KEYS_FOLDER, filename + '.enckey')
        encrypt_aes_key(aes_key, output_file=encrypted_key_path)
        aes_key = None
        store.update(file_id, status='ENCRYPTED', file_hash=file_hash,
                     encrypted_key_path=encrypted_key_path, encrypted_path=encrypted_path)

        stage = 'IPFS'
        cid = upload_file_to_pinata(encrypted_path, name=filename + '.encrypted')
        if not cid:
            raise RuntimeError('IPFS_UPLOAD_FAILED')
        store.update(file_id, status='IPFS_UPLOADED', cid=cid)

        stage = 'BLOCKCHAIN'
        def on_prepared(tx_hash, owner_address):
            store.update(file_id, status='CHAIN_PENDING', tx_hash=tx_hash,
                         owner_address=owner_address)

        chain_result = register_file_on_chain(cid, filename, on_prepared=on_prepared)
        if chain_result['status'] != 1:
            raise RuntimeError('CHAIN_REVERTED')
        stage = 'REGISTRY'
        record = store.update(file_id, status='REGISTERED',
                              tx_hash=chain_result['tx_hash'],
                              owner_address=chain_result['owner_address'],
                              block_number=chain_result['block_number'])
        return jsonify({"message": "암호화·IPFS 업로드·블록체인 등록 완료", **record}), 200
    except ChainPending:
        record = store.update(file_id, status='CHAIN_PENDING', error='CONFIRMATION_REQUIRED')
        return jsonify({"message": "거래 확인이 필요합니다. 재업로드하지 말고 tx_hash를 조회하세요.",
                        **record}), 202
    except Exception:
        # Do not return external exception strings, which can contain credentials.
        record = store.update(file_id, status='FAILED', failed_stage=stage,
                              error=stage + '_FAILED')
        return jsonify({"message": "처리에 실패했습니다. 저장된 단계와 결과를 확인하세요.",
                        **record}), (502 if stage in ('IPFS', 'BLOCKCHAIN') else 500)
    finally:
        aes_key = None
        if os.path.exists(plain_path):
            os.remove(plain_path)


@app.route('/files', methods=['GET'])
def list_files():
    registry = get_registry().list()
    return jsonify({
        "files": registry,
        "count": len(registry)
    })


# ---------------------------------------------------------
# 기능 A: 복약 설명 AI
# 흐름: 처방 약물명 -> DUR API(공식 사실) -> LLM(쉬운 말로 설명)
# ---------------------------------------------------------
@app.route('/medication-info', methods=['POST'])
def medication_info():
    if os.environ.get('MEDICATION_MODEL', 'sentence-fhe') == 'sentence-fhe':
        from tiny_fhe.sentence_model import generate
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or set(payload) != {'prescription'}:
            return jsonify(error='prescription 문자열 하나가 필요합니다.'), 400
        try:
            return jsonify(generate(payload['prescription']))
        except ValueError as exc:
            return jsonify(error=str(exc)), 422
        except Exception:
            return jsonify(error='문장 모델 실행 실패: Python 3.12 및 TenSEAL 설치를 확인하세요.'), 503
    # The supplied local model is now the default. No plaintext API fallback.
    if os.environ.get('MEDICATION_MODEL', 'tiny-fhe') == 'tiny-fhe':
        return predict_prescription()
    if os.environ.get('MEDICATION_MODEL') != 'claude':
        return jsonify(error='UNKNOWN_MEDICATION_MODEL'), 503
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify(error='INVALID_PRESCRIPTION_OBJECT'), 400

    # 개인정보 보호: 약물명/진단명만 받는다. 환자 이름·ID 등은 이 엔드포인트로
    # 애초에 넘기지 않도록 프론트/호출부에서 걸러야 한다.
    drug_name = payload.get('prescription')
    diagnosis = payload.get('diagnosis')  # 선택

    if not drug_name:
        return jsonify({"error": "약물명(prescription)이 필요합니다."}), 400

    # 1. 공식 DUR 데이터 조회 (사실 확보)
    try:
        dur_data = fetch_dur_taboo_info(drug_name)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    # 2. LLM으로 쉬운 말 설명 생성 (설명만 담당, 사실은 새로 만들지 않음)
    try:
        explanation = generate_medication_explanation(drug_name, dur_data, diagnosis)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"AI 설명 생성 중 오류가 발생했습니다: {str(e)}"}), 502

    return jsonify({
        "drug_name": drug_name,
        "dur_data": dur_data,          # 원본 공식 데이터 (카드 하단 근거 표시용으로 활용 가능)
        "explanation": explanation,     # LLM이 생성한 쉬운 설명 (효능/복용법/주의사항/병용금기)
        "disclaimer": "이 정보는 참고용이며 정확한 복용법은 의료진·약사와 상담하세요."
    }), 200


# ---------------------------------------------------------
# 기능 B: 건강 통계 리포트 AI
# 흐름: 여러 visit 기록 -> pandas 통계(추세/변화율/이상치) -> LLM(자연어 리포트)
# ---------------------------------------------------------
@app.route('/health-report', methods=['POST'])
def health_report():
    payload = request.get_json(silent=True) or {}

    # visits 예시:
    # [{"date": "2026-06-01", "systolic": 128, "diastolic": 82, "glucose": 95}, ...]
    visits = payload.get('visits')

    # lifestyle 예시 (스키마 확장분, 가은님과 논의 필요):
    # {"exercise_frequency": "주 2회", "rehab_status": "재활 진행 중"}
    lifestyle = payload.get('lifestyle')

    if not visits or not isinstance(visits, list):
        return jsonify({"error": "visits(방문 기록 배열)가 필요합니다."}), 400

    # 1. pandas로 통계 처리 (사실 확보 - LLM은 이 숫자를 벗어난 값을 말하면 안 됨)
    try:
        stats = build_health_stats(visits)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"통계 처리 중 오류가 발생했습니다: {str(e)}"}), 500

    # 2. LLM으로 자연어 리포트 생성 (통계 요약값만 전달, 원본 방문기록/개인정보는 전달 안 함)
    try:
        report_text = generate_health_report(stats, lifestyle)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"AI 리포트 생성 중 오류가 발생했습니다: {str(e)}"}), 502

    return jsonify({
        "stats": stats,
        "report": report_text,
        "disclaimer": "이 리포트는 참고용이며 정확한 진단과 치료는 반드시 의료진과 상담하세요."
    }), 200


if __name__ == '__main__':
    app.run(debug=False, port=5000)
