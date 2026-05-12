FROM python:3.12-slim

# Non-root user für Sicherheit
RUN useradd --create-home --shell /bin/bash botuser

WORKDIR /app

# Abhängigkeiten zuerst (besseres Layer-Caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Quellcode kopieren
COPY src/ src/

# config/ wird als Volume eingehängt — nicht im Image
USER botuser

CMD ["python", "-m", "src.main"]
