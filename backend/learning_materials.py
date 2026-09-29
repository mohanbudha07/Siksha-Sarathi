"""Private file handling for teacher-uploaded Learning Materials."""

import mimetypes
import os
from pathlib import Path
from uuid import uuid4

from werkzeug.utils import secure_filename


ALLOWED_MATERIAL_EXTENSIONS = frozenset({".pdf", ".doc", ".docx", ".ppt", ".pptx"})
MAX_MATERIAL_FILES = 10
MAX_MATERIAL_FILE_BYTES = 25 * 1024 * 1024
MAX_MATERIAL_REQUEST_BYTES = 100 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 64 * 1024


def configure_learning_material_upload_root(repository_root):
    configured_root = os.getenv("LEARNING_MATERIAL_UPLOAD_DIR", "").strip()
    if configured_root:
        upload_root = configured_root
        if not os.path.isabs(upload_root):
            upload_root = os.path.join(repository_root, upload_root)
    else:
        upload_root = os.path.join(repository_root, "uploads", "learning_materials")
    return os.path.abspath(upload_root)


class MaterialUploadError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def safe_storage_path(upload_root, filename):
    """Resolve a generated storage key and reject paths outside the private root."""
    root = Path(upload_root).resolve()
    candidate = (root / str(filename)).resolve()
    try:
        if os.path.commonpath((str(root), str(candidate))) != str(root):
            raise ValueError("Storage key resolves outside the upload root")
    except ValueError as error:
        raise ValueError("Storage key resolves outside the upload root") from error
    return candidate


def stage_material_uploads(files, upload_root):
    """Validate files and write them to uniquely named private staging files."""
    selected_files = [item for item in files if item and item.filename]
    if len(selected_files) > MAX_MATERIAL_FILES:
        raise MaterialUploadError("A Learning Material can include at most 10 files.")
    if not selected_files:
        return []

    root = Path(upload_root)
    root.mkdir(parents=True, exist_ok=True)
    staged = []
    try:
        for upload in selected_files:
            submitted_basename = Path(upload.filename.replace("\\", "/")).name
            extension = Path(submitted_basename).suffix.lower()
            if extension not in ALLOWED_MATERIAL_EXTENSIONS:
                raise MaterialUploadError("That file type is not supported.")
            original_filename = secure_filename(submitted_basename)
            if (
                not original_filename
                or Path(original_filename).suffix.lower() != extension
                or not Path(original_filename).stem
            ):
                original_filename = f"document{extension}"
            if len(original_filename) > 255:
                stem = original_filename[:-len(extension)]
                original_filename = f"{stem[:255 - len(extension)]}{extension}"

            stored_filename = f"{uuid4().hex}{extension}"
            staging_filename = f".stage-{uuid4().hex}.tmp"
            item = {
                "original_filename": original_filename,
                "stored_filename": stored_filename,
                "mime_type": str(
                    upload.mimetype
                    or mimetypes.guess_type(original_filename)[0]
                    or "application/octet-stream"
                )[:255],
                "size_bytes": 0,
                "staging_filename": staging_filename,
                "moved": False,
            }
            staged.append(item)
            staging_path = safe_storage_path(root, staging_filename)
            with staging_path.open("xb") as output:
                while True:
                    chunk = upload.stream.read(UPLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    item["size_bytes"] += len(chunk)
                    if item["size_bytes"] > MAX_MATERIAL_FILE_BYTES:
                        raise MaterialUploadError(
                            "Each file must be 25 MB or smaller.", 413
                        )
                    output.write(chunk)

        return staged
    except Exception:
        cleanup_staged_material_uploads(root, staged)
        raise


def finalize_staged_material_uploads(upload_root, staged):
    root = Path(upload_root)
    for item in staged:
        source = safe_storage_path(root, item["staging_filename"])
        destination = safe_storage_path(root, item["stored_filename"])
        os.replace(source, destination)
        item["moved"] = True


def cleanup_staged_material_uploads(upload_root, staged):
    for item in staged:
        filenames = [item.get("staging_filename")]
        if item.get("moved"):
            filenames.append(item.get("stored_filename"))
        for filename in filenames:
            if not filename:
                continue
            try:
                safe_storage_path(upload_root, filename).unlink(missing_ok=True)
            except (OSError, ValueError):
                continue