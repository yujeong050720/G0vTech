"""Synthetic browser demo; intentionally does not expose the legacy Flask API."""
import base64
import hmac
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from uuid import UUID

from Crypto.Cipher import PKCS1_OAEP
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from flask import Flask, jsonify, request

from blockchain_registry import get_web3, register_file_on_chain, ChainPending
from cloud_store import CloudStore
from IPFS_upload import upload_file_to_pinata
from medical_encryptor import encrypt_medical_data
from tiny_fhe.sentence_model import TRAINING_PAIRS

REQUIRED = ('PINATA_JWT', 'WEB3_PROVIDER_URL', 'CONTRACT_ADDRESS', 'PRIVATE_KEY',
            'SUPABASE_URL', 'SUPABASE_SECRET_KEY', 'HOSPITAL_PUBLIC_KEY_B64',
            'DEMO_ACCESS_CODE')


def generate(prompt):
    # Release TenSEAL's large native allocations after each phase to fit small
    # free servers. The evaluator still receives only the public request ZIP.
    script = str(Path(__file__).parent / 'tiny_fhe' / 'sentence_model.py')
    child_env = {k: v for k, v in os.environ.items()
                 if k.upper() in ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP',
                                  'TMPDIR', 'LANG', 'LC_ALL')}
    child_env.update(PYTHONIOENCODING='utf-8', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    with tempfile.TemporaryDirectory(prefix='cloud-ckks-') as folder:
        public = str(Path(folder) / 'public_request.zip')
        response = str(Path(folder) / 'response.zip')
        for args in [('prepare', folder, prompt), ('evaluate', public, response),
                     ('finish', folder, response)]:
            result = subprocess.run([sys.executable, script, *args], check=True,
                                    capture_output=True, timeout=180,
                                    encoding='utf-8', env=child_env)
        answer = json.loads(result.stdout)
        answer['execution'] = 'server-encrypt/separate-process-ckks/server-decrypt'
        return answer


def configuration_ready():
    return all(os.environ.get(k) for k in REQUIRED) and len(os.environ['DEMO_ACCESS_CODE']) >= 16


def process_run(store, run_id, prompt):
    payload = {'status': 'RUNNING', 'storage': {'status': 'PENDING'},
               'ai': {'status': 'PENDING'}}
    store.save(run_id, payload)
    stage = 'CONFIGURATION'
    try:
        # Check before IPFS upload and, critically, before wallet signing.
        w3 = get_web3()
        if w3.eth.chain_id != 11155111:
            raise ValueError('SEPOLIA_ONLY')
        address = w3.to_checksum_address(os.environ['CONTRACT_ADDRESS'])
        if not w3.eth.get_code(address):
            raise ValueError('CONTRACT_NOT_FOUND')
        public_key = RSA.import_key(base64.b64decode(os.environ['HOSPITAL_PUBLIC_KEY_B64'], validate=True))
        if public_key.has_private() or public_key.size_in_bits() < 2048:
            raise ValueError('PUBLIC_KEY_REQUIRED')
        stage = 'ENCRYPTION'
        encrypted, key, digest = encrypt_medical_data({'patient_ref': 'demo-' + run_id,
                                                      'prescription': prompt})
        wrapped = PKCS1_OAEP.new(public_key, hashAlgo=SHA256).encrypt(key)
        del key
        # Only the hospital's public key goes to the cloud. Preserve wrapped AES
        # keys outside the ephemeral server disk before uploading ciphertext.
        payload.update(wrapped_key_b64=base64.b64encode(wrapped).decode(),
                       ciphertext_sha256=digest, patient_ref='demo-' + run_id)
        payload['storage'] = {'status': 'ENCRYPTED'}
        store.save(run_id, payload)
        stage = 'IPFS'
        with tempfile.TemporaryDirectory(prefix='medical-demo-') as folder:
            path = Path(folder) / (run_id + '.encrypted')
            path.write_bytes(encrypted)
            cid = upload_file_to_pinata(str(path), name=path.name)
        if not cid:
            raise RuntimeError('IPFS_FAILED')
        payload['storage'].update(status='IPFS_UPLOADED', cid=cid)
        store.save(run_id, payload)
        stage = 'BLOCKCHAIN'

        def prepared(tx_hash, owner_address):
            payload['storage'].update(status='CHAIN_PENDING', tx_hash=tx_hash)
            store.save(run_id, payload)

        chain = register_file_on_chain(cid, run_id, on_prepared=prepared)
        if chain['status'] != 1:
            raise RuntimeError('CHAIN_FAILED')
        payload['storage'].update(status='REGISTERED', tx_hash=chain['tx_hash'])
    except ChainPending:
        payload['storage'].update(status='CHAIN_PENDING')
    except Exception:
        payload['storage'].update(status='FAILED', failed_stage=stage)
    store.save(run_id, payload)
    try:
        payload['ai'] = {'status': 'SUCCEEDED', **generate(prompt)}
    except Exception:
        payload['ai'] = {'status': 'FAILED'}
    payload['status'] = 'DONE'
    store.save(run_id, payload)


def create_app(store=None, processor=process_run):
    app = Flask(__name__, static_folder='static', static_url_path='/assets')
    app.config['MAX_CONTENT_LENGTH'] = 2048
    gate = threading.Lock()
    limiter = threading.Lock()
    attempts = deque()
    active = set()

    def db():
        return store if store is not None else CloudStore()

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.before_request
    def auth():
        if not request.path.startswith('/api/'):
            return None
        secret = os.environ.get('DEMO_ACCESS_CODE', '')
        if len(secret) < 16:
            return jsonify(error='NOT_CONFIGURED'), 503
        supplied = request.headers.get('X-Demo-Code', '')
        if not hmac.compare_digest(supplied.encode(), secret.encode()):
            return jsonify(error='INVALID_CODE'), 401

    @app.get('/')
    def index():
        return app.send_static_file('index.html')

    @app.get('/health')
    def health():
        return jsonify(status='ok', configured=configuration_ready())

    @app.post('/api/runs')
    def start():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) != {'prescription'} or data['prescription'] not in [p for p, _ in TRAINING_PAIRS]:
            return jsonify(error='SYNTHETIC_INPUT_ONLY'), 400
        if not configuration_ready():
            return jsonify(error='NOT_CONFIGURED'), 503
        with limiter:
            now = time.monotonic()
            while attempts and now - attempts[0] > 60:
                attempts.popleft()
            if len(attempts) >= 3:
                return jsonify(error='RATE_LIMIT'), 429
            attempts.append(now)
        if not gate.acquire(blocking=False):
            return jsonify(error='BUSY'), 429
        try:
            metadata = db()
            row = metadata.claim()
            if not row:
                gate.release()
                return jsonify(error='DAILY_LIMIT'), 429
            run_id = str(UUID(row['id']))
            active.add(run_id)

            def worker():
                try:
                    processor(metadata, run_id, data['prescription'])
                except Exception:
                    # Persist a failure if possible. Never retry a transaction
                    # automatically when its broadcast state may be uncertain.
                    try:
                        old = metadata.get(run_id)['payload']
                        metadata.save(run_id, dict(old, status='INTERRUPTED'))
                    except Exception:
                        pass
                finally:
                    active.discard(run_id)
                    gate.release()

            threading.Thread(target=worker, daemon=True).start()
            return jsonify(id=run_id), 202
        except Exception:
            gate.release()
            return jsonify(error='METADATA_UNAVAILABLE'), 503

    @app.get('/api/runs/<run_id>')
    def result(run_id):
        try:
            UUID(run_id)
        except ValueError:
            return jsonify(error='NOT_FOUND'), 404
        try:
            row = db().get(run_id)
        except Exception:
            return jsonify(error='METADATA_UNAVAILABLE'), 503
        if not row:
            return jsonify(error='NOT_FOUND'), 404
        payload = row['payload']
        status = payload.get('status', 'PENDING')
        if status in ('PENDING', 'RUNNING') and run_id not in active:
            status = 'INTERRUPTED'
        # Keys and internal metadata must never appear in the public response.
        return jsonify(id=run_id, status=status, storage=payload.get('storage', {}),
                       ai=payload.get('ai', {}))

    return app


app = create_app()

if __name__ == '__main__':
    from waitress import serve
    serve(app, host=os.environ.get('HOST', '127.0.0.1'),
          port=int(os.environ.get('PORT', '7860')), threads=4)
