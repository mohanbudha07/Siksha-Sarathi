"""Unit tests for online and offline Study Assistant behavior."""

from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assistant import generate_answer


class FakeModels:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.call = None

    def generate_content(self, **kwargs):
        self.call = kwargs
        if self.error:
            raise self.error
        return self.response


class AssistantTests(unittest.TestCase):
    def test_no_api_key_uses_offline_helper(self):
        with patch.dict('os.environ', {'GEMINI_API_KEY': ''}):
            subject, answer, mode = generate_answer('Explain photosynthesis')
        self.assertEqual(subject, 'Science')
        self.assertIn('sunlight', answer)
        self.assertEqual(mode, 'offline')

    def test_injected_gemini_client_returns_model_answer(self):
        models = FakeModels(types.SimpleNamespace(text='A clear model answer.'))
        client = types.SimpleNamespace(models=models)
        subject, answer, mode = generate_answer(
            'Solve this mathematics equation', client=client,
            model='test-model'
        )
        self.assertEqual((subject, answer, mode), (
            'Mathematics', 'A clear model answer.', 'gemini'
        ))
        self.assertEqual(models.call['model'], 'test-model')
        self.assertIn('Nepal', models.call['config']['system_instruction'])

    def test_gemini_error_uses_offline_helper(self):
        client = types.SimpleNamespace(
            models=FakeModels(error=RuntimeError('quota exhausted'))
        )
        subject, answer, mode = generate_answer('What is democracy?', client=client)
        self.assertEqual(subject, 'Social Studies')
        self.assertIn('voting', answer)
        self.assertEqual(mode, 'offline')


if __name__ == '__main__':
    unittest.main()
