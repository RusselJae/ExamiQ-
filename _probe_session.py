import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()
from django.test import Client
c = Client()
s = c.session
print('session ok', dict(s))
