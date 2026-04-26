web: python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn aflora_natural.wsgi --workers 2 --bind 0.0.0.0:$PORT
