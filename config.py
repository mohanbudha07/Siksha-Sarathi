import os

class Config:
    # Flask Settings
    SECRET_KEY = "SikshaSarathi@2026_FYP"

    # MySQL Configuration
    MYSQL_HOST = "localhost"
    MYSQL_USER = "root"
    MYSQL_PASSWORD = ""
    MYSQL_DB = "siksha_sarathi"
    MYSQL_CURSORCLASS = "DictCursor"

    # Base Directory
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

    # Upload Configuration
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

    MATERIAL_UPLOAD_FOLDER = os.path.join(
        UPLOAD_FOLDER,
        "materials"
    )

    HOMEWORK_UPLOAD_FOLDER = os.path.join(
        UPLOAD_FOLDER,
        "homework"
    )

    PROFILE_UPLOAD_FOLDER = os.path.join(
        UPLOAD_FOLDER,
        "profiles"
    )

    # Maximum Upload Size (16 MB)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # Allowed File Extensions
    ALLOWED_EXTENSIONS = {
        "pdf",
        "doc",
        "docx",
        "ppt",
        "pptx",
        "jpg",
        "jpeg",
        "png"
    }

    # Flask Debug Mode
    DEBUG = True