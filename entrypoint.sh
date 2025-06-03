#!/bin/sh

# Wait for the database to be ready
echo "Waiting for database..."
while ! pg_isready -h $DB_HOST -p $DB_PORT -U $DB_USER; do
  sleep 1
done
echo "Database is ready!"

# Apply database migrations
echo "Applying migrations..."
python manage.py migrate

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Create default admin user if not exists
echo "Checking for admin user..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
admin_exists = User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME', role='admin').exists()
print(admin_exists)
" | grep -q "True"
ADMIN_EXISTS=$?

if [ $ADMIN_EXISTS -ne 0 ]; then
  echo "Creating admin role user..."
  python manage.py shell -c "
from django.contrib.auth import get_user_model
import os
User = get_user_model()
if not User.objects.filter(username=os.environ['DJANGO_SUPERUSER_USERNAME']).exists():
    user = User.objects.create_user(
        username=os.environ['DJANGO_SUPERUSER_USERNAME'],
        email=os.environ.get('DJANGO_SUPERUSER_EMAIL', ''),
        password=os.environ['DJANGO_SUPERUSER_PASSWORD'],
        role='admin',
        is_staff=True,
        is_superuser=True
    )
    print(f'Admin user {user.username} created successfully!')
else:
    user = User.objects.get(username=os.environ['DJANGO_SUPERUSER_USERNAME'])
    if user.role != 'admin':
        user.role = 'admin'
        user.is_staff = True
        user.is_superuser = True
        user.save()
        print(f'Updated {user.username} to admin role!')
    else:
        print(f'Admin user {user.username} already exists with admin role.')
"
else
  echo "Admin user already exists."
fi

# Execute the CMD
exec "$@"
