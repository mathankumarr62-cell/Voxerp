"""Regressions for course codes observed in Gemma's student_name field."""
import pytest

from intelligence.intent_engine import IntentEngine
from intelligence.rbac import authorize_request


@pytest.mark.parametrize('code', ['AD3491', 'CS1234', 'it25201'])
@pytest.mark.parametrize('table', ['marks', 'attendance'])
@pytest.mark.parametrize('field', ['student_name', 'student_id'])
def test_self_course_misclassified_as_name_reaches_own_data(code, table, field):
    engine = IntentEngine.__new__(IntentEngine)
    engine.gemma_available = True
    engine.client = None
    intent = {'action': 'read', 'table': table,
              'filters': {'student_name': None, 'student_id': None, 'subject': None}}
    intent['filters'][field] = code
    engine._generate_gemma_intent = lambda **kwargs: intent
    text = f'Show my {code} {table}'
    result = engine.parse(text, 'student', {})
    assert result['filters']['student_name'] is None
    assert result['filters']['student_id'] is None
    assert result['filters']['subject'] == code
    auth = authorize_request('917', 'student', result, text)
    assert auth['allowed'] and auth['target_student_id'] == '917'


def test_recovery_preserves_existing_subject_and_explicit_identity():
    engine = IntentEngine.__new__(IntentEngine)
    intent = {'action': 'read', 'table': 'marks',
              'filters': {'student_name': 'AD3491', 'student_id': '2',
                          'subject': 'Distributed Computing'}}
    text = 'Show my AD3491 marks for student 2'
    result = engine._recover_gemma_entities(text, intent)
    assert result['filters']['student_id'] == '2'
    assert result['filters']['subject'] == 'Distributed Computing'
    assert not authorize_request('917', 'student', result, text)['allowed']


@pytest.mark.parametrize('text,name', [
    ('Show student AD3491 marks', 'AD3491'),
    ('Show my AD3491 marks for Bob Smith', 'Bob Smith'),
])
def test_course_recovery_does_not_clear_other_student_names(text, name):
    engine = IntentEngine.__new__(IntentEngine)
    intent = {'action': 'read', 'table': 'marks',
              'filters': {'student_name': name, 'student_id': None, 'subject': None}}
    result = engine._recover_gemma_entities(text, intent)
    assert result['filters']['student_name'] == name
    assert not authorize_request('917', 'student', result, text)['allowed']
