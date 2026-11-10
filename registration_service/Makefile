PYTHON ?= ../.venv/bin/python
MYSQL ?= mysql -h 127.0.0.1 -u root

gen:
	mkdir -p generated
	$(PYTHON) -m grpc_tools.protoc -I ../proto --python_out=generated --grpc_python_out=generated ../proto/registration.proto ../proto/event.proto

db:
	$(MYSQL) < schema.sql

dev: gen
	PYTHONPATH=generated $(PYTHON) server.py

.PHONY: gen db dev
