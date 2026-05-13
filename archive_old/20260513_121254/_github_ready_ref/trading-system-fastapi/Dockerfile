FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY db ./db
COPY docs ./docs
COPY prompts ./prompts
COPY SPEC.md AGENTS.md ROADMAP.md ./

RUN pip install --no-cache-dir --upgrade pip &&     pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
