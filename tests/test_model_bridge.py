import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import app


class ModelBridgeTests(unittest.TestCase):
    def setUp(self):
        # This regression suite targets the original toy vocabulary regardless
        # of the user's editable training corpus.
        corpus = patch('tiny_fhe.demo.CORPUS', [
            '나는 음악 좋아해', '나는 음악 좋아해',
            '우리는 산책 즐겨', '우리는 산책 즐겨'])
        corpus.start()
        self.addCleanup(corpus.stop)
        env = patch.dict(os.environ, LOCAL_API_TOKEN='x'*32, MEDICATION_MODEL='tiny-fhe', ENABLE_TINY_FHE_DEMO='1')
        env.start()
        self.addCleanup(env.stop)
        self.client = app.test_client()
        self.auth = {'Authorization': 'Bearer ' + 'x'*32}

    def test_requires_token(self):
        self.assertEqual(self.client.post('/medication-info', json={'prescription':'음악'}).status_code, 401)

    def test_unknown_drug_does_not_call_external_ai(self):
        with patch('app.fetch_dur_taboo_info') as dur, patch('app.generate_medication_explanation') as llm:
            result = self.client.post('/medication-info', headers=self.auth, json={'prescription':'가상약품명'})
        self.assertEqual(result.status_code, 422)
        self.assertFalse(result.json['medical_llm'])
        dur.assert_not_called()
        llm.assert_not_called()

    def test_invalid_payloads_and_browser_origin(self):
        for value in ([], {'prescription':42}, {'prescription':' '}, {'prescription':'음악','patient_name':'x'}):
            self.assertEqual(self.client.post('/medication-info', headers=self.auth, json=value).status_code, 400)
        self.assertEqual(self.client.post('/medication-info', headers={**self.auth, 'Origin':'http://example.com'}, json={'prescription':'음악'}).status_code, 401)

    def test_capabilities(self):
        result = self.client.get('/private-ai/demo/capabilities', headers=self.auth)
        self.assertEqual(result.status_code, 200)
        self.assertIn('음악', result.json['supported_vocabulary'])

    def test_real_model_through_prescription_api(self):
        result = self.client.post('/medication-info', headers=self.auth, json={'prescription':'음악 산책'})
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual([r['prediction'] for r in result.json['predictions']], ['좋아해','즐겨'])
        self.assertTrue(result.json['verified'])
        self.assertIsNone(result.json['explanation'])
        self.assertEqual(result.headers['Cache-Control'], 'no-store')

    def test_real_model_single_input(self):
        result = self.client.post('/medication-info', headers=self.auth, json={'prescription':'음악'})
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(len(result.json['predictions']), 1)
        self.assertEqual(result.json['predictions'][0]['prediction'], '좋아해')

    def test_original_file_exchange(self):
        from tiny_fhe.demo import evaluate
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, TINY_FHE_CLIENT_DIR=folder):
            created = self.client.post('/private-ai/demo/jobs', headers=self.auth, json={'tokens':['음악','산책']})
            self.assertEqual(created.status_code, 201, created.json)
            downloaded = self.client.get(created.json['request_url'], headers=self.auth)
            request_file = Path(folder)/'request.zip'
            request_file.write_bytes(downloaded.data)
            downloaded.close()
            result_file = Path(folder)/'response.zip'
            report = evaluate(request_file, result_file)
            self.assertFalse(report['server_has_secret_key'])
            response = self.client.post('/private-ai/demo/jobs/'+created.json['job_id']+'/result', headers=self.auth,
                data={'file':(io.BytesIO(result_file.read_bytes()),'response.zip')})
            self.assertEqual(response.status_code, 200, response.json)
            self.assertTrue(response.json['passed'])
