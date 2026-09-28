from unittest import TestCase, mock

from api.services import VoxERPService


class ServiceLifecycleTests(TestCase):
    def test_intent_engine_is_created_on_first_access_and_can_be_replaced(self):
        with mock.patch("api.services.IntentEngine") as engine_factory:
            service = VoxERPService()
            engine_factory.assert_not_called()

            first_engine = service.engine
            engine_factory.assert_called_once_with()
            self.assertIs(first_engine, engine_factory.return_value)

            replacement = mock.Mock()
            service.engine = replacement
            self.assertIs(service.engine, replacement)
