from django.db import models


class ConsumedConfirmation(models.Model):
    """Atomic replay protection shared by all workers and login sessions."""

    token_digest = models.CharField(max_length=64, primary_key=True)
    consumed_at = models.DateTimeField(auto_now_add=True)
