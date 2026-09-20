import unittest
from unittest.mock import patch
import os
from app import app
from tiny_fhe.sentence_model import TRAINING_PAIRS, generate, encode, train


class SentenceModelTests(unittest.TestCase):
    def test_encrypted_sentence_a(self):
        prompt, expected = TRAINING_PAIRS[0]
        result = generate(prompt)
        self.assertEqual(result['explanation'], expected)
        self.assertTrue(result['verified'])
        self.assertLess(result['max_error'], 0.001)

    def test_sentence_b_via_api(self):
        prompt, expected = TRAINING_PAIRS[1]
        with patch.dict(os.environ, MEDICATION_MODEL='sentence-fhe', LOCAL_API_TOKEN='x'*32):
            response = app.test_client().post('/medication-info',
                headers={'Authorization':'Bearer '+'x'*32}, json={'prescription':prompt})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['explanation'], expected)

    def test_unknown_sentence_rejected(self):
        with self.assertRaises(ValueError):
            encode('모르는 약 처방', train())
