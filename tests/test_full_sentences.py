import os
import unittest
from unittest.mock import patch
from app import app


class FullSentenceTests(unittest.TestCase):
    def test_all_matching_sentences_are_returned(self):
        with patch.dict(os.environ, LOCAL_API_TOKEN='x'*32, MEDICATION_MODEL='tiny-fhe'):
            result = app.test_client().post('/medication-info',
                headers={'Authorization': 'Bearer '+'x'*32},
                json={'prescription': '타이레놀'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json['sentences'], ['타이레놀 음주 금지', '타이레놀 담배 금지'])
        self.assertEqual(result.json['execution'], 'local-corpus-lookup')
        self.assertFalse(result.json['clinically_validated'])
        self.assertEqual(len(result.json['predictions']), 2)

    def test_particle_and_multiword_subject(self):
        from tiny_fhe.prescription import corpus_sentences
        self.assertEqual(corpus_sentences('바라크루드'), ['바라크루드는 식사 전후 2시간에 복용'])
        self.assertEqual(corpus_sentences('판피린 큐'), ['판피린 큐는 음주 금지'])

    def test_no_partial_match(self):
        from tiny_fhe.prescription import corpus_sentences
        self.assertEqual(corpus_sentences('타이'), [])
