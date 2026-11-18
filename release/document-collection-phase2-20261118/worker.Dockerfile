FROM alahsa-local-worker

COPY app/models.py /app/app/models.py
COPY app/documents.py /app/app/documents.py
COPY app/celery_app.py /app/app/celery_app.py
COPY app/document_collection /app/app/document_collection
COPY migrations/versions/0028_document_collection_engine.py /app/migrations/versions/0028_document_collection_engine.py
