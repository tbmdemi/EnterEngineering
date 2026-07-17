.PHONY: run reset-demo check
run:
	docker compose up --build
reset-demo:
	docker compose down -v
	docker compose up --build
check:
	python3 -m unittest discover -s tests
	cd frontend && npm run build
