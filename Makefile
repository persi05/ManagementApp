.PHONY: up down build rebuild restart logs shell migrate migrations test clean

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

rebuild:
	docker compose up -d --build

restart:
	docker compose restart

logs:
	docker compose logs -f

shell:
	docker compose exec web sh

migrate:
	docker compose exec web python manage.py migrate

migrations:
	docker compose exec web python manage.py makemigrations

test:
	docker compose exec web python manage.py test

reset:
	docker compose down -v --remove-orphans