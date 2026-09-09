"""Production WSGI entry point.

Run behind the college reverse proxy with a production WSGI server, not
``python app.py``.  See DEPLOYMENT.md.
"""

from app import app
