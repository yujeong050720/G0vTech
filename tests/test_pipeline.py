import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import app as server
import blockchain_registry as chain
from registry_store import RegistryStore
from medical_encryptor import encrypt_medical_data
from Crypto.Cipher import AES


class StoreTests(unittest.TestCase):
    def test_concurrent_creates_and_legacy_import(self):
        with tempfile.TemporaryDirectory() as folder:
            store = RegistryStore(Path(folder) / 'registry.db')
            with ThreadPoolExecutor(max_workers=4) as executor:
                list(executor.map(lambda n: store.create(str(n), status='RECEIVED'), range(20)))
            source = Path(folder) / 'registry.json'
            source.write_text(json.dumps([{'filename': 'old.json', 'cid': 'old'}]))
            store.import_legacy(source)
            store.import_legacy(source)
            self.assertEqual(len(store.list()), 21)
            self.assertEqual(store.list()[-1]['status'], 'LEGACY_UNVERIFIED')


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name in ('uploads', 'encrypted', 'keys'):
            (root / name).mkdir()
        self.root = root
        self.patches = [
            patch.dict(server.app.config, TESTING=True, REGISTRY_DATABASE=str(root/'registry.db'),
                       UPLOAD_FOLDER=str(root/'uploads')),
            patch.object(server, 'ENCRYPTED_FOLDER', str(root/'encrypted')),
            patch.object(server, 'KEYS_FOLDER', str(root/'keys')),
            patch.object(server, 'ensure_hospital_keys'),
            patch.object(server, 'encrypt_aes_key'),
            patch.object(server, 'upload_file_to_pinata', return_value='test-cid'),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.client = server.app.test_client()

    def upload(self, data=b'{"visits": []}'):
        return self.client.post('/upload', data={'file': (io.BytesIO(data), 'same.json')})

    def test_success_and_unique_names(self):
        def register(cid, filename, on_prepared):
            on_prepared('0xtest', 'owner')
            return dict(status=1, tx_hash='0xtest', owner_address='owner', block_number=1)
        with patch.object(server, 'register_file_on_chain', side_effect=register):
            first, second = self.upload(), self.upload()
        self.assertEqual(first.status_code, 200)
        self.assertNotEqual(first.json['filename'], second.json['filename'])
        self.assertEqual(first.json['status'], 'REGISTERED')
        self.assertEqual(self.client.get('/files').json['count'], 2)
        self.assertEqual(list((self.root/'uploads').iterdir()), [])

    def test_invalid_json(self):
        for data in (b'{broken', b'[]'):
            self.assertEqual(self.upload(data).status_code, 400)
        self.assertEqual(list((self.root/'uploads').iterdir()), [])

    def test_ipfs_failure_preserves_encryption_metadata(self):
        with patch.object(server, 'upload_file_to_pinata', return_value=None):
            result = self.upload()
        self.assertEqual(result.status_code, 502)
        self.assertEqual(result.json['failed_stage'], 'IPFS')
        self.assertIn('file_hash', result.json)

    def test_chain_failure_preserves_cid(self):
        with patch.object(server, 'register_file_on_chain', side_effect=RuntimeError('secret')):
            result = self.upload()
        self.assertEqual(result.status_code, 502)
        self.assertEqual(result.json['cid'], 'test-cid')
        self.assertNotIn('secret', result.get_data(as_text=True))

    def test_pending_preserves_hash(self):
        def pending(cid, filename, on_prepared):
            on_prepared('0xpending', 'owner')
            raise chain.ChainPending()
        with patch.object(server, 'register_file_on_chain', side_effect=pending):
            result = self.upload()
        self.assertEqual(result.status_code, 202)
        self.assertEqual(result.json['status'], 'CHAIN_PENDING')
        self.assertEqual(result.json['tx_hash'], '0xpending')

    def test_unsuccessful_receipt_is_not_registered(self):
        with patch.object(server, 'register_file_on_chain', return_value={'status': 0}):
            result = self.upload()
        self.assertEqual(result.status_code, 502)
        self.assertEqual(result.json['status'], 'FAILED')


class ChainTests(unittest.TestCase):
    def test_abi_loads(self):
        self.assertTrue(any(x.get('name') == 'registerFile' for x in chain._load_abi()))

    def test_receipt_failure_and_callback_before_send(self):
        w3 = MagicMock()
        account = w3.eth.account.from_key.return_value
        account.sign_transaction.return_value = SimpleNamespace(raw_transaction=b'signed')
        w3.eth.wait_for_transaction_receipt.return_value = SimpleNamespace(status=0)
        order = []
        w3.eth.send_raw_transaction.side_effect = lambda raw: order.append('send')
        with patch.dict(os.environ, PRIVATE_KEY='test'), patch.object(chain, 'get_web3', return_value=w3), patch.object(chain, 'get_contract'):
            with self.assertRaises(chain.ChainReverted):
                chain.register_file_on_chain('cid', 'file', lambda *args: order.append('persist'))
        self.assertEqual(order, ['persist', 'send'])

    def test_rpc_failure_remains_pending(self):
        w3 = MagicMock()
        w3.eth.account.from_key.return_value.sign_transaction.return_value = SimpleNamespace(raw_transaction=b'signed')
        w3.eth.send_raw_transaction.side_effect = TimeoutError()
        with patch.dict(os.environ, PRIVATE_KEY='test'), patch.object(chain, 'get_web3', return_value=w3), patch.object(chain, 'get_contract'):
            with self.assertRaises(chain.ChainPending):
                chain.register_file_on_chain('cid', 'file')


class CryptoTests(unittest.TestCase):
    def test_roundtrip_and_tampering(self):
        data = {'visits': [], 'note': '테스트'}
        encrypted, key, digest = encrypt_medical_data(data)
        cipher = AES.new(key, AES.MODE_GCM, nonce=encrypted[:16])
        plain = cipher.decrypt_and_verify(encrypted[32:], encrypted[16:32])
        self.assertEqual(json.loads(plain), data)
        cipher = AES.new(key, AES.MODE_GCM, nonce=encrypted[:16])
        altered = encrypted[32:-1] + bytes([encrypted[-1] ^ 1])
        with self.assertRaises(ValueError):
            cipher.decrypt_and_verify(altered, encrypted[16:32])


if __name__ == '__main__':
    unittest.main()
