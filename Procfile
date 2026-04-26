web: gunicorn aflora_natural.wsgi --workers 2 --bind 0.0.0.0:$PORT
release: python manage.py migrate --noinput
