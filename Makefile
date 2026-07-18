.PHONY: setup run reset-demo check
setup:
	python3 -m venv .venv
	.venv/bin/pip install -r backend/requirements.txt
	cd frontend && npm ci
run:
	docker compose up --build
reset-demo:
	docker compose down -v
	docker compose up --build
check:
	.venv/bin/python -m unittest discover -s tests
	PYTHONPYCACHEPREFIX=/tmp/careguard-pycache .venv/bin/python -m compileall -q backend
	docker compose config -q
	cd frontend && npm run build
