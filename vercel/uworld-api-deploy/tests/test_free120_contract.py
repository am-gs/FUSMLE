import pathlib
import sys
import unittest

API_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

from free120_questions import FREE120_QUESTIONS
from index import app


class Free120ContractTests(unittest.TestCase):
    def auth_headers(self):
        client = app.test_client()
        import uuid
        email = f"free120-{uuid.uuid4().hex}@example.com"
        response = client.post('/api/register', json={'email': email, 'password': 'TestPass123!', 'name': 'Free 120 User'})
        self.assertIn(response.status_code, (200, 201))
        return {'Authorization': f"Bearer {response.get_json()['token']}"}

    def test_static_free120_dataset_shape(self):
        self.assertEqual(len(FREE120_QUESTIONS), 119)
        self.assertEqual(FREE120_QUESTIONS[0]['id'], 'free120_2021_q001')
        self.assertEqual(FREE120_QUESTIONS[-1]['id'], 'free120_2021_q119')
        self.assertEqual(len({q['id'] for q in FREE120_QUESTIONS}), 119)
        for question in FREE120_QUESTIONS:
            self.assertEqual(question['source_form'], 'free120_2021')
            self.assertEqual(question['exam_type'], 'free120')
            self.assertTrue(question['text'].strip())
            self.assertGreaterEqual(len(question['options']), 4)
            self.assertIn(question['correct_answer'], {option['id'] for option in question['options']})

    def test_free120_structured_table_questions_are_present(self):
        questions_by_id = {question['id']: question for question in FREE120_QUESTIONS}
        for question_id in [
            'free120_2021_q003',
            'free120_2021_q007',
            'free120_2021_q028',
            'free120_2021_q049',
            'free120_2021_q054',
            'free120_2021_q062',
            'free120_2021_q067',
            'free120_2021_q090',
            'free120_2021_q092',
            'free120_2021_q094',
        ]:
            self.assertIn('tables', questions_by_id[question_id])
            self.assertIn('[[table:0]]', questions_by_id[question_id]['text'])
        for question_id in ['free120_2021_q005', 'free120_2021_q038', 'free120_2021_q047', 'free120_2021_q094']:
            self.assertIn('option_table', questions_by_id[question_id])

    def test_free120_options_have_no_block_header_artifacts(self):
        import re
        pattern = re.compile(r'BLOCK\s+\d,\s+ITEMS\s+\d+-\d+')
        for question in FREE120_QUESTIONS:
            for option in question['options']:
                self.assertIsNone(pattern.search(option['text']), f"{question['id']} option {option['letter']} contains a block header")

    def test_generate_free120_persists_ordered_session(self):
        client = app.test_client()
        headers = self.auth_headers()
        response = client.post('/api/qbank/generate-free120', json={}, headers=headers)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        expected_ids = [question['id'] for question in FREE120_QUESTIONS]
        self.assertEqual(payload['format'], 'free120')
        self.assertEqual(payload['totalQuestions'], 119)
        self.assertEqual(payload['questionIds'], expected_ids)

        state = client.get(f"/api/qbank/test/{payload['testSessionId']}/state", headers=headers)
        self.assertEqual(state.status_code, 200)
        self.assertEqual(state.get_json()['questionIds'], expected_ids)

    def test_free120_boundary_question_fetches(self):
        client = app.test_client()
        headers = self.auth_headers()
        payload = client.post('/api/qbank/generate-free120', json={}, headers=headers).get_json()
        for index in [0, 1, 19, 20, 59, 118]:
            response = client.get(f"/api/qbank/test/{payload['testSessionId']}/question/{index}", headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()['question']['id'], payload['questionIds'][index])

    def test_free120_question_payload_includes_structured_tables(self):
        client = app.test_client()
        headers = self.auth_headers()
        payload = client.post('/api/qbank/generate-free120', json={}, headers=headers).get_json()
        q3 = client.get(f"/api/qbank/test/{payload['testSessionId']}/question/2", headers=headers).get_json()['question']
        self.assertEqual(q3['tables'][0]['columns'][0], 'Agonist')
        q5 = client.get(f"/api/qbank/test/{payload['testSessionId']}/question/4", headers=headers).get_json()['question']
        self.assertEqual(q5['option_table']['columns'], ['Blood Pressure (mm Hg)', 'Pulse (/min)', 'Jugular Venous Pressure', 'Pulsus Paradoxus'])


if __name__ == '__main__':
    unittest.main()
