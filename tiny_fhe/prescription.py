"""Bridge the existing prescription JSON input to the supplied CKKS model."""
import hmac
import os
from pathlib import Path
import tempfile
import threading

from flask import jsonify, request

_inference_lock = threading.Lock()


def corpus_sentences(name):
    """Exact subject lookup of user-provided text, not generated medical advice."""
    from tiny_fhe.demo import CORPUS
    words = name.split()
    if not words:
        return []
    matches = []
    for sentence in CORPUS:
        parts = sentence.split()
        if len(parts) <= len(words):
            continue
        subject = parts[:len(words)]
        if subject[:-1] == words[:-1] and subject[-1] in (
            words[-1], words[-1] + '은', words[-1] + '는'
        ):
            matches.append(sentence)
    return list(dict.fromkeys(matches))


def authorize():
    token = os.environ.get('LOCAL_API_TOKEN', '')
    if len(token) < 32:
        return jsonify(error='LOCAL_API_TOKEN_NOT_CONFIGURED'), 503
    expected = ('Bearer ' + token).encode()
    if request.headers.get('Origin') or not hmac.compare_digest(
        request.headers.get('Authorization', '').encode(), expected
    ):
        return jsonify(error='UNAUTHORIZED'), 401


def predict():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) - {'prescription', 'diagnosis'}:
        return jsonify(error='INVALID_PRESCRIPTION_OBJECT'), 400
    prescription = payload.get('prescription')
    if not isinstance(prescription, str) or not 1 <= len(prescription.strip()) <= 200:
        return jsonify(error='PRESCRIPTION_REQUIRED'), 400
    if payload.get('diagnosis') is not None and (
        not isinstance(payload['diagnosis'], str) or len(payload['diagnosis']) > 500
    ):
        return jsonify(error='INVALID_DIAGNOSIS'), 400
    sentences = corpus_sentences(prescription.strip())
    if sentences:
        return jsonify(
            model='user-corpus-lookup', medical_llm=False,
            execution='local-corpus-lookup', clinically_validated=False,
            sentences=sentences, explanation='\n'.join(sentences),
            predictions=[{'input': prescription.strip(), 'prediction': sentence}
                         for sentence in sentences],
            message='사용자가 등록한 실험 문장입니다. 의학적으로 검증된 복약 안내가 아닙니다.'
        )
    from tiny_fhe.demo import train, prepare, evaluate, finish
    tokens = prescription.strip().split()
    vocab = train()['vocab']
    if not 1 <= len(tokens) <= 2 or any(t not in vocab for t in tokens):
        return jsonify(error='MODEL_INPUT_UNSUPPORTED', model='synthetic-bigram',
                       medical_llm=False, supported_vocabulary=vocab,
                       message='연결된 모델의 어휘에 없는 입력입니다. 약 설명은 생성하지 않았습니다.'), 422
    if not _inference_lock.acquire(blocking=False):
        return jsonify(error='MODEL_BUSY'), 429
    try:
        # Keep the original two-vector model unchanged. Duplicate a single input
        # only for its fixed batch shape, then return one prediction.
        with tempfile.TemporaryDirectory(prefix='kakao-model-') as directory:
            folder = Path(directory)
            prepare(folder, tokens if len(tokens) == 2 else tokens * 2)
            response = folder / 'response.zip'
            evaluate(folder / 'public_request.zip', response)
            report = finish(folder, response)
            predictions = report['results'][:len(tokens)]
        return jsonify(model='synthetic-bigram', medical_llm=False,
                       execution='local-ckks-roundtrip', verified=report['passed'],
                       predictions=predictions, explanation=None,
                       message='모델 연결 결과입니다. 이 모델은 약 설명을 생성하지 않습니다.')
    except ImportError:
        return jsonify(error='TENSEAL_NOT_INSTALLED'), 503
    except Exception:
        return jsonify(error='MODEL_INFERENCE_FAILED'), 502
    finally:
        _inference_lock.release()
