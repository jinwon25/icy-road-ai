"""근거 파일의 SHA-256 계산."""
import hashlib
from pathlib import Path
def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()
