PYTHON ?= ../.venv/bin/python

gen:
	mkdir -p generated
	$(PYTHON) -m grpc_tools.protoc -I ../proto --python_out=generated --grpc_python_out=generated ../proto/event.proto ../proto/registration.proto

dev: gen
	PYTHONPATH=generated $(PYTHON) app.py

.PHONY: gen dev
