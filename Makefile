.PHONY: install test lint report run docker-build docker-run compose-up clean

install:
	pip install -r requirements.txt

test:
	pytest --maxfail=1 --disable-warnings -q

lint:
	ruff check src/ tests/

report:
	python -m src.reporting.build_report

run:
	streamlit run streamlit_app/app.py

docker-build:
	docker build -t hydraulic-dashboard -f streamlit_app/Dockerfile .

docker-run: docker-build
	docker run -p 8501:8501 hydraulic-dashboard

compose-up:
	docker compose up --build

clean:
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .coverage
