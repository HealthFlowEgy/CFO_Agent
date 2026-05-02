.PHONY: deploy logs rebuild stop restart

deploy:
	@echo "Starting deployment via scripts/deploy.sh..."
	sudo ./scripts/deploy.sh

logs:
	docker compose logs -f

logs-api:
	docker compose logs -f api

logs-web:
	docker compose logs -f web

rebuild:
	docker compose up -d --build

stop:
	docker compose down

restart:
	docker compose restart
