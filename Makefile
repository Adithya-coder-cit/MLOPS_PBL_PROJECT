.PHONY: setup test lint api train

setup:
	python -m venv .venv
	.venv/Scripts/python -m pip install --upgrade pip
	.venv/Scripts/python -m pip install -r requirements.txt

test:
	.venv/Scripts/python -m pytest tests/ -v

lint:
	.venv/Scripts/python -m ruff check src/ api/ training/ inference/ tests/

api:
	.venv/Scripts/python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

train:
	.venv/Scripts/python training/train.py
