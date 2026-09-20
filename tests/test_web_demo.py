import base64
import copy
import os
import threading
import time
import unittest
from unittest.mock import patch, MagicMock
from uuid import uuid4

from Crypto.Cipher import PKCS1_OAEP, AES
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from web_demo import create_app, process_run, REQUIRED


class FakeStore:
    def __init__(self):
        self.rows = {}
        self.limit = False

    def claim(self):
        if self.limit:
            return None
        run_id = str(uuid4())
        self.rows[run_id] = {'id': run_id, 'payload': {'status': 'PENDING'}}
        return self.get(run_id)

    def save(self, run_id, payload):
        self.rows[run_id]['payload'] = copy.deepcopy(payload)

    def get(self, run_id):
        return copy.deepcopy(self.rows.get(run_id))


class WebDemoTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {k: 'test-value-123456789' for k in REQUIRED})
        env.start()
        self.addCleanup(env.stop)
        self.store = FakeStore()
        self.headers = {'X-Demo-Code': os.environ['DEMO_ACCESS_CODE']}

    def test_public_surface_and_auth(self):
        client = create_app(self.store).test_client()
        with client.get('/') as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(client.get('/health').status_code, 200)
        self.assertEqual(client.get('/upload').status_code, 404)
        self.assertEqual(client.post('/api/runs', json={'prescription': '가상약A 1정 처방'}).status_code, 401)
        response = client.post('/api/runs', headers=self.headers, json={'prescription': '실제 환자 데이터'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.store.rows, {})

    def test_quota_busy_and_private_result_fields(self):
        done = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)

        def process(store, run_id, prompt):
            release.wait(5)
            store.save(run_id, {'status': 'DONE', 'wrapped_key_b64': 'never-public',
                                'storage': {'status': 'REGISTERED'}, 'ai': {'status': 'SUCCEEDED'}})
            done.set()

        client = create_app(self.store, process).test_client()
        args = {'headers': self.headers, 'json': {'prescription': '가상약A 1정 처방'}}
        response = client.post('/api/runs', **args)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(client.post('/api/runs', **args).status_code, 429)
        release.set()
        self.assertTrue(done.wait(5))
        result = client.get('/api/runs/' + response.json['id'], headers=self.headers)
        self.assertEqual(result.json['status'], 'DONE')
        self.assertNotIn('wrapped_key_b64', result.json)
        self.assertNotIn('never-public', result.text)
        quota_client = create_app(self.store).test_client()
        self.store.limit = True
        self.assertEqual(quota_client.post('/api/runs', **args).json['error'], 'DAILY_LIMIT')

    def test_restart_recognizes_interrupted_job(self):
        row = self.store.claim()
        client = create_app(self.store).test_client()
        result = client.get('/api/runs/' + row['id'], headers=self.headers)
        self.assertEqual(result.json['status'], 'INTERRUPTED')

    def test_mainnet_never_uploads_or_signs(self):
        run_id = self.store.claim()['id']
        w3 = MagicMock()
        w3.eth.chain_id = 1
        with patch('web_demo.get_web3', return_value=w3), \
             patch('web_demo.upload_file_to_pinata') as upload, \
             patch('web_demo.register_file_on_chain') as chain, \
             patch('web_demo.generate', return_value={'verified': True}):
            process_run(self.store, run_id, '가상약A 1정 처방')
        upload.assert_not_called()
        chain.assert_not_called()
        self.assertEqual(self.store.get(run_id)['payload']['storage']['failed_stage'], 'CONFIGURATION')

    def test_wrapped_key_survives_ephemeral_file_cleanup(self):
        from pathlib import Path
        key = RSA.generate(2048)
        os.environ['HOSPITAL_PUBLIC_KEY_B64'] = base64.b64encode(key.publickey().export_key()).decode()
        run_id = self.store.claim()['id']
        w3 = MagicMock()
        w3.eth.chain_id = 11155111
        w3.eth.get_code.return_value = b'code'
        captured = {}

        def upload(path, name):
            captured['ciphertext'] = Path(path).read_bytes()
            captured['path'] = path
            return 'test-cid'

        def chain(cid, name, on_prepared):
            on_prepared('test-tx', 'test-owner')
            self.assertEqual(self.store.get(run_id)['payload']['storage']['tx_hash'], 'test-tx')
            return {'status': 1, 'tx_hash': 'test-tx'}

        with patch('web_demo.get_web3', return_value=w3), \
             patch('web_demo.upload_file_to_pinata', side_effect=upload), \
             patch('web_demo.register_file_on_chain', side_effect=chain), \
             patch('web_demo.generate', return_value={'verified': True}):
            process_run(self.store, run_id, '가상약A 1정 처방')
        row = self.store.get(run_id)['payload']
        aes_key = PKCS1_OAEP.new(key, hashAlgo=SHA256).decrypt(base64.b64decode(row['wrapped_key_b64']))
        data = captured['ciphertext']
        clear = AES.new(aes_key, AES.MODE_GCM, nonce=data[:16]).decrypt_and_verify(data[32:], data[16:32])
        self.assertIn('가상약A', clear.decode())
        self.assertFalse(Path(captured['path']).exists())
        self.assertEqual(row['storage']['status'], 'REGISTERED')


if __name__ == '__main__':
    unittest.main()
