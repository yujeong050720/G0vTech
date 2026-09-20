"""Local-only file exchange API for the real CKKS toy model."""
import json
import os
from pathlib import Path
import re
import uuid

from flask import Blueprint, jsonify, request, send_file

bp = Blueprint('tiny_fhe', __name__, url_prefix='/private-ai/demo')


def root():
    return Path(os.environ.get('TINY_FHE_CLIENT_DIR', 'local_data/tiny-client-jobs')).resolve()


def job_path(job_id):
    if not re.fullmatch(r'[0-9a-f]{32}', job_id):
        return None
    path = root() / job_id
    return path if path.is_dir() else None


@bp.get('/capabilities')
def capabilities():
    from tiny_fhe.demo import train
    return jsonify(model='synthetic-bigram', medical_llm=False,
                   supported_vocabulary=train()['vocab'],
                   workflow='local-encrypt/colab-evaluate/local-decrypt',
                   enabled=os.environ.get('ENABLE_TINY_FHE_DEMO') == '1')


@bp.post('/jobs')
def create_job():
    if os.environ.get('ENABLE_TINY_FHE_DEMO') != '1':
        return jsonify(error='DEMO_DISABLED'), 503
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != {'tokens'}:
        return jsonify(error='Provide tokens: exactly two known vocabulary words'), 400
    from tiny_fhe.demo import prepare
    job_id = uuid.uuid4().hex
    path = root() / job_id
    try:
        metadata = prepare(path, payload['tokens'])
    except ImportError:
        return jsonify(error='TENSEAL_NOT_INSTALLED'), 503
    except ValueError:
        return jsonify(error='UNSUPPORTED_TOKENS'), 400
    return jsonify(job_id=job_id, model='synthetic-bigram', medical_llm=False,
                   request_url=f'/private-ai/demo/jobs/{job_id}/request', **metadata), 201


@bp.get('/jobs/<job_id>/request')
def download_request(job_id):
    path = job_path(job_id)
    if path is None or not (path / 'public_request.zip').is_file():
        return jsonify(error='NOT_FOUND'), 404
    return send_file(path / 'public_request.zip', as_attachment=True, download_name='public_request.zip')


@bp.post('/jobs/<job_id>/result')
def upload_result(job_id):
    path = job_path(job_id)
    if path is None or not (path / 'secret.key').is_file():
        return jsonify(error='NOT_FOUND'), 404
    if 'file' not in request.files:
        return jsonify(error='RESULT_ZIP_REQUIRED'), 400
    body = request.files['file'].read(2 * 1024 * 1024 + 1)
    if len(body) > 2 * 1024 * 1024:
        return jsonify(error='RESULT_TOO_LARGE'), 413
    import io
    import zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            if set(z.namelist()) != {'output_0.bin', 'output_1.bin', 'server_report.json'}:
                raise ValueError()
            if len(z.infolist()) != 3 or sum(x.file_size for x in z.infolist()) > 2 * 1024 * 1024:
                raise ValueError()
        response = path / 'response.zip'
        response.write_bytes(body)
        from tiny_fhe.demo import finish
        result = finish(path, response)
    except Exception:
        return jsonify(error='INVALID_OR_MISMATCHED_RESULT'), 400
    return jsonify(result)
