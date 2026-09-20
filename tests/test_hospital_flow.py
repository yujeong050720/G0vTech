import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from Crypto.PublicKey import RSA
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.Hash import SHA256
from app import app
import hospital_service as hospital


class HospitalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, LOCAL_API_TOKEN='x'*32,
                         HOSPITAL_DATA_DIR=self.temp.name)
        env.start()
        self.addCleanup(env.stop)
        # External services are mocked in tests only, never in application code.
        ipfs = patch.object(hospital, 'upload_file_to_pinata', return_value='test-cid')
        chain = patch.object(hospital, 'register_file_on_chain', return_value={
            'status':1, 'tx_hash':'test-tx', 'owner_address':'test-owner', 'block_number':1})
        ipfs.start()
        chain.start()
        self.addCleanup(ipfs.stop)
        self.addCleanup(chain.stop)
        self.client = app.test_client()
        self.auth = {'Authorization': 'Bearer '+'x'*32}

    def upload(self, patient='demo-1', prompt='가상약A 1정 처방'):
        document = {'patient_ref':patient, 'prescription':prompt}
        return self.client.post('/hospital/prescriptions', headers=self.auth,
            data={'file':(io.BytesIO(json.dumps(document).encode()),'prescription.json')})

    def test_real_encryption_ai_and_patient_record(self):
        result = self.upload()
        self.assertEqual(result.status_code, 201, result.json)
        self.assertEqual(result.json['storage']['status'], 'REGISTERED')
        self.assertTrue(result.json['storage']['distributed_ledger'])
        self.assertTrue(result.json['ai']['verified'])
        self.assertIn('음주를 피하세요', result.json['ai']['explanation'])
        record = hospital.registry().list()[0]
        private = RSA.import_key((Path(self.temp.name)/'hospital_private.pem').read_bytes())
        key = PKCS1_OAEP.new(private, hashAlgo=SHA256).decrypt(Path(record['encrypted_key_path']).read_bytes())
        encrypted = Path(record['encrypted_path']).read_bytes()
        original = AES.new(key, AES.MODE_GCM, nonce=encrypted[:16]).decrypt_and_verify(encrypted[32:], encrypted[16:32])
        self.assertEqual(json.loads(original)['patient_ref'], 'demo-1')
        self.assertNotIn('prescription', record)
        self.assertNotIn('explanation', record)
        listing = self.client.get('/hospital/patients/demo-1/records', headers=self.auth).json
        self.assertEqual(listing['count'], 1)
        self.assertEqual(self.client.get('/hospital/patients/other/records', headers=self.auth).json['count'], 0)

    def test_storage_failure_does_not_block_ai(self):
        with patch.dict(os.environ, HOSPITAL_STORAGE_BACKEND='live'), \
             patch.object(hospital, 'wrap_key'), \
             patch.object(hospital, 'upload_file_to_pinata', return_value=None), \
             patch.object(hospital, 'generate', return_value={'explanation':'test'}) as ai:
            result = self.upload()
        self.assertEqual(result.status_code, 207)
        self.assertEqual(result.json['storage']['status'], 'FAILED')
        self.assertEqual(result.json['ai']['status'], 'SUCCEEDED')
        ai.assert_called_once_with('가상약A 1정 처방')

    def test_ai_failure_does_not_lose_record(self):
        with patch.object(hospital, 'wrap_key'), patch.object(hospital, 'generate', side_effect=ValueError()):
            result = self.upload(prompt='미지원 문장')
        self.assertEqual(result.status_code, 207)
        self.assertEqual(result.json['storage']['status'], 'REGISTERED')
        self.assertEqual(result.json['ai']['status'], 'UNSUPPORTED_INPUT')
        self.assertEqual(len(hospital.registry().list()), 1)

    def test_live_contract_receives_only_random_id_and_cid(self):
        def register(cid, filename, on_prepared):
            self.assertEqual(cid, 'test-cid')
            self.assertNotIn('demo-1', filename)
            on_prepared('test-tx', 'test-owner')
            return {'status':1,'tx_hash':'test-tx','owner_address':'test-owner','block_number':1}
        with patch.dict(os.environ, HOSPITAL_STORAGE_BACKEND='live'), \
             patch.object(hospital, 'wrap_key'), \
             patch.object(hospital, 'upload_file_to_pinata', return_value='test-cid'), \
             patch.object(hospital, 'register_file_on_chain', side_effect=register), \
             patch.object(hospital, 'generate', return_value={'explanation':'test'}):
            result = self.upload()
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.json['storage']['status'], 'REGISTERED')

    def test_auth_and_invalid_json(self):
        self.assertEqual(self.client.get('/hospital/patients/demo-1/records').status_code, 401)
        response = self.client.post('/hospital/prescriptions', headers=self.auth,
            data={'file':(io.BytesIO(b'{}'),'prescription.json')})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(hospital.registry().list(), [])
