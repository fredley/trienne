rm db.sqlite3 && rm lanes/migrations/0* && ./manage.py makemigrations && ./manage.py migrate && ./manage.py loaddata fixture.json
