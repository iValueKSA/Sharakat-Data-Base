FROM opportunity-documents-mvp-api:furas-booklet-20261118

COPY app/main.py /app/app/main.py
COPY app/models.py /app/app/models.py
COPY app/celery_app.py /app/app/celery_app.py
COPY app/document_collection /app/app/document_collection
COPY migrations/versions/0028_document_collection_engine.py /app/migrations/versions/0028_document_collection_engine.py
