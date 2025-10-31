from flask import Flask, request, jsonify, render_template
import os
import logging
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from azure.storage.blob import BlobServiceClient, ContentSettings


# Configuration via environment variables
STORAGE_ACCOUNT_URL = os.getenv("STORAGE_ACCOUNT_URL")
IMAGES_CONTAINER = os.getenv("IMAGES_CONTAINER", "lanternfly-images")
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")


# Flask app setup
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB


# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lanternfly")


# Azure Blob Clients
if AZURE_STORAGE_CONNECTION_STRING:
    blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
elif STORAGE_ACCOUNT_URL:
    # If using account URL without credentials, listing may work for public container; upload requires creds
    blob_service_client = BlobServiceClient(account_url=STORAGE_ACCOUNT_URL)
else:
    raise RuntimeError("Missing storage configuration. Set AZURE_STORAGE_CONNECTION_STRING or STORAGE_ACCOUNT_URL.")

container_client = blob_service_client.get_container_client(IMAGES_CONTAINER)


def _is_image_upload(file_storage) -> bool:
    mimetype = (file_storage.mimetype or "").lower()
    return mimetype.startswith("image/")


def _timestamped_name(original_filename: str) -> str:
    safe = secure_filename(original_filename or "upload")
    # Ensure extension is preserved if present
    now_utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{now_utc}-{safe}"


@app.post("/api/v1/upload")
def upload():
    try:
        if "file" not in request.files:
            return jsonify(ok=False, error="Missing file"), 400

        f = request.files["file"]
        if f.filename == "":
            return jsonify(ok=False, error="Empty filename"), 400

        if not _is_image_upload(f):
            return jsonify(ok=False, error="Only image/* content types are allowed"), 400

        blob_name = _timestamped_name(f.filename)

        # Upload to Azure Blob Storage (overwrite allowed)
        content_settings = ContentSettings(content_type=f.mimetype)
        container_client.upload_blob(
            name=blob_name,
            data=f.stream,
            overwrite=True,
            content_settings=content_settings,
        )

        blob_url = f"{container_client.url}/{blob_name}"
        logger.info("Uploaded %s", blob_url)
        return jsonify(ok=True, url=blob_url)

    except Exception as exc:
        logger.exception("Upload failed")
        return jsonify(ok=False, error=str(exc)), 500


@app.get("/api/v1/gallery")
def gallery():
    try:
        # List blobs and build public URLs
        urls = []
        blobs = container_client.list_blobs()
        for b in blobs:
            urls.append(f"{container_client.url}/{b.name}")

        # Optionally sort newest-first by name assuming timestamp prefix
        urls.sort(reverse=True)
        return jsonify(ok=True, gallery=urls)
    except Exception as exc:
        logger.exception("Gallery fetch failed")
        return jsonify(ok=False, error=str(exc)), 500


@app.get("/api/v1/health")
def health():
    return jsonify(ok=True)


@app.get("/")
def index():
    return render_template("index.html")
