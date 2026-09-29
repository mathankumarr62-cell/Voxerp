"""Regressions for the current acceptance review; no live model or ERP."""
from unittest.mock import Mock, patch

import pytest
from django.core import signing

from api.services import Identity, VoxERPService
from api.views import PENDING_SALT
from intelligence.intent_engine import IntentEngine
from voice.stt import normalize_course_codes
from voice.tts import prepare_speech


@pytest.mark.parametrize('text,code', [
    ('AD3491', 'AD3491'), ('AD 3491', 'AD3491'),
    ('AD three four nine one', 'AD3491'), ('A D three four nine one', 'AD3491'),
    ('CS1234', 'CS1234'), ('C S one two three four', 'CS1234'),
    ('IT two five two zero one', 'IT25201'),
])
def test_generic_course_normalization(text, code):
    assert normalize_course_codes(text) == code
    engine = IntentEngine(client=object())
    engine.client = None
    engine.gemma_available = True
    engine._generate_gemma_intent = Mock(return_value={
        'action': 'read', 'table': 'marks', 'filters': {}})
    with patch('api.services.db_adapter.get_marks', return_value={'status': 'no_data', 'message': 'No marks available'}) as read:
        result = VoxERPService(engine).query(Identity('self', 'student'), f'Show my {text} marks')
    read.assert_called_once_with('self', code)
    assert prepare_speech(result['reply_text'])
    assert code in engine._generate_gemma_intent.call_args.kwargs['text']


@pytest.mark.parametrize('text', ['Show student 917 marks', 'period 1', 'Distributed Computing', 'student 1234'])
def test_normalization_preserves_other_entities(text):
    assert normalize_course_codes(text) == text


def test_attendance_without_subject_reads_authenticated_student():
    engine = Mock()
    engine.parse.return_value = {'action': 'read', 'table': 'attendance', 'filters': {}}
    with patch('api.services.db_adapter.get_attendance', return_value={'status': 'no_data', 'message': 'No attendance available'}) as read:
        VoxERPService(engine).query(Identity('self', 'student'), 'What is my attendance?')
    read.assert_called_once_with('self', None)


@pytest.mark.parametrize('environment', [None, '', 'prod', ' Production '])
def test_service_environment_fails_closed(monkeypatch, environment):
    if environment is None:
        monkeypatch.delenv('VOXERP_ENV', raising=False)
    else:
        monkeypatch.setenv('VOXERP_ENV', environment)
    engine = Mock()
    service = VoxERPService(engine)
    assert service.query(Identity('self', 'student'), 'my marks')['status'] == 503
    assert service.confirm(Identity('self', 'student'), {}, 'yes')['status'] == 503
    engine.parse.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize('operation', ['query', 'confirm'])
def test_internal_value_errors_are_not_returned(client, django_user_model, operation):
    user = django_user_model.objects.create_user(username='self')
    client.force_login(user)
    token = signing.dumps({'user_id': user.pk, 'pending': {}}, salt=PENDING_SALT)
    payload = {'text': 'my marks'} if operation == 'query' else {'confirm': 'yes', 'pending': token}
    with patch(f'api.views.service.{operation}', side_effect=ValueError('private configuration detail')):
        response = client.post(f'/api/{operation}/', data=payload, content_type='application/json')
    assert response.status_code == 500
    assert 'private configuration detail' not in response.content.decode()
