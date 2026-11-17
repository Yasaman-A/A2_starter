PYTHON ?= python3

install:
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -r requirements.txt

gen:
	$(MAKE) -C event_service gen
	$(MAKE) -C registration_service gen
	$(MAKE) -C gateway gen

db:
	$(MAKE) -C event_service db
	$(MAKE) -C registration_service db

dev:
	trap 'kill 0' INT TERM; \
	$(MAKE) -C event_service dev & \
	$(MAKE) -C registration_service dev & \
	$(MAKE) -C gateway dev & \
	wait

.PHONY: install gen db dev
