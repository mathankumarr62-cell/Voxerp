from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def dashboard(request):
    """Authenticated ERP-assistant web UI."""
    return render(request, "api/dashboard.html")
