import hashlib
from pathlib import Path

from flask import request


def configure_static_cache(app):
    # Changed files get new URLs, so browsers can cache each version for a year.
    folder = Path(app.static_folder)
    files = {}
    versions = {}
    for path in folder.rglob("*"):
        if path.is_file():
            name = path.relative_to(folder).as_posix()
            files[name] = path

    def asset_version(filename):
        path = files.get(filename)
        if path is None:
            return None
        try:
            modified = path.stat().st_mtime_ns
            if filename not in versions or versions[filename][0] != modified:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
                versions[filename] = (modified, digest)
            return versions[filename][1]
        except OSError:
            return None

    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600

    @app.url_defaults
    def add_asset_version(endpoint, values):
        if endpoint == "static":
            version = asset_version(values.get("filename"))
            if version:
                values.setdefault("v", version)

    @app.after_request
    def cache_static_files(response):
        if request.endpoint == "static" and response.status_code in (200, 304):
            filename = (request.view_args or {}).get("filename")
            version = asset_version(filename)
            if version and request.args.get("v") == version:
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response
