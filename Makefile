.PHONY: setup run reset-demo check

ifeq ($(OS),Windows_NT)
CHECK_COMMAND = powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1
else
CHECK_COMMAND = sh scripts/check.sh
endif
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
	$(CHECK_COMMAND)
