"""Hospital-side experimental orchestration. Never deploy as the FHE evaluator."""
import json
import os
from pathlib import Path
import re
import threading
from uuid import uuid4

from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Hash import SHA256
from flask import Blueprint, jsonify, request

from medical_encryptor import encrypt_medical_data
from registry_store import RegistryStore
from IPFS_upload import upload_file_to_pinata
from blockchain_registry import register_file_on_chain, ChainPending
from tiny_fhe.sentence_model import generate
from tiny_fhe.prescription import authorize

bp = Blueprint('hospital', __name__, url_prefix='/hospital')
_lock = threading.Lock()


@bp.before_request
def authentication():
    return authorize()


@bp.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


def root():
    path = Path(os.environ.get('HOSPITAL_DATA_DIR', 'local_data/hospital')).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def registry():
    return RegistryStore(root() / 'records.sqlite3')


def wrap_key(key, destination):
    private_path = root() / 'hospital_private.pem'
    public_path = root() / 'hospital_public.pem'
    if private_path.exists() != public_path.exists():
        raise RuntimeError('Incomplete key pair; restore backup instead of regenerating')
    if not private_path.exists():
        rsa = RSA.generate(3072)
        private_path.write_bytes(rsa.export_key(format='PEM', pkcs=8))
        public_path.write_bytes(rsa.publickey().export_key())
    public = RSA.import_key(public_path.read_bytes())
    destination.write_bytes(PKCS1_OAEP.new(public, hashAlgo=SHA256).encrypt(key))


def process(document):
    backend = "live"
    record_id = str(uuid4())
    store = registry()
    store.create(record_id, patient_ref=document['patient_ref'], backend=backend,
                 status='RECEIVED', ai_status='PENDING')
    storage_result = {'status': 'FAILED', 'backend': backend}
    stage = 'ENCRYPTION'
    try:
        encrypted, aes_key, digest = encrypt_medical_data(document)
        file_path = root() / (record_id + '.encrypted')
        key_path = root() / (record_id + '.enckey')
        file_path.write_bytes(encrypted)
        try:
            wrap_key(aes_key, key_path)
        finally:
            aes_key = None
        store.update(record_id, status='ENCRYPTED', ciphertext_sha256=digest,
                     encrypted_path=str(file_path), encrypted_key_path=str(key_path))
        stage = 'IPFS'
        cid = upload_file_to_pinata(str(file_path), name=record_id+'.encrypted')
        if not cid:
            raise RuntimeError('IPFS upload failed')
        store.update(record_id, status='IPFS_UPLOADED', cid=cid)
        storage_result['cid'] = cid
        stage = 'BLOCKCHAIN'
        def prepared(tx_hash, owner_address):
            storage_result.update(tx_hash=tx_hash, owner_address=owner_address)
            store.update(record_id, status='CHAIN_PENDING', tx_hash=tx_hash,
                         owner_address=owner_address)
        chain = register_file_on_chain(cid, record_id, on_prepared=prepared)
        if chain['status'] != 1:
            raise RuntimeError('Chain registration failed')
        store.update(record_id, status='REGISTERED', tx_hash=chain['tx_hash'],
                     owner_address=chain['owner_address'], block_number=chain['block_number'])
        storage_result.update(status='REGISTERED', distributed_ledger=True,
                              tx_hash=chain['tx_hash'], owner_address=chain['owner_address'])
    except ChainPending:
        storage_result.update(status='CHAIN_PENDING', error='CONFIRMATION_REQUIRED')
        store.update(record_id, status='CHAIN_PENDING', error='CONFIRMATION_REQUIRED')
    except Exception:
        storage_result.update(status='FAILED', failed_stage=stage)
        store.update(record_id, status='FAILED', failed_stage=stage)

    # Independent from storage success. Only the prescription sentence is
    # encoded/encrypted for the evaluator; patient_ref stays hospital-side.
    try:
        ai_result = {'status': 'SUCCEEDED', **generate(document['prescription'])}
    except ValueError:
        ai_result = {'status': 'UNSUPPORTED_INPUT', 'error': '학습된 가상 처방 문장을 입력하세요.'}
    except Exception:
        ai_result = {'status': 'FAILED', 'error': 'FHE_INFERENCE_FAILED'}
    # Do not persist plaintext AI output or prescription in the metadata DB.
    store.update(record_id, ai_status=ai_result['status'])
    complete = storage_result['status'] == 'REGISTERED' and ai_result['status'] == 'SUCCEEDED'
    return {'record_id': record_id, 'patient_ref': document['patient_ref'],
            'storage': storage_result, 'ai': ai_result}, (201 if complete else 207)


@bp.post('/prescriptions')
def upload():
    file = request.files.get('file')
    if file is None or not (file.filename or '').lower().endswith('.json'):
        return jsonify(error='처방전 JSON 파일을 file 항목으로 업로드하세요.'), 400
    try:
        raw = file.stream.read(64 * 1024 + 1)
        if len(raw) > 64 * 1024:
            return jsonify(error='처방전은 64 KiB 이하로 업로드하세요.'), 413
        document = json.loads(raw.decode('utf-8-sig'))
        if not isinstance(document, dict) or set(document) != {'patient_ref', 'prescription'}:
            raise ValueError()
        if not isinstance(document['patient_ref'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', document['patient_ref']):
            raise ValueError()
        if not isinstance(document['prescription'], str) or not 1 <= len(document['prescription']) <= 200:
            raise ValueError()
    except (ValueError, UnicodeError):
        return jsonify(error='patient_ref와 prescription 문자열이 필요합니다.'), 400
    # Serialize this experimental single-hospital key/wallet flow.
    if not _lock.acquire(blocking=False):
        return jsonify(error='HOSPITAL_BUSY'), 429
    try:
        result, status = process(document)
        return jsonify(result), status
    finally:
        _lock.release()


@bp.get('/patients/<patient_ref>/records')
def records(patient_ref):
    # Hospital-wide token only; not a patient login/consent implementation.
    entries = [row for row in registry().list() if row.get('patient_ref') == patient_ref]
    public_fields = ('id', 'patient_ref', 'backend', 'status', 'ai_status', 'created_at',
                     'updated_at', 'cid', 'tx_hash', 'ciphertext_sha256', 'storage_ref', 'failed_stage')
    return jsonify(records=[{k: row[k] for k in public_fields if k in row} for row in entries], count=len(entries))
