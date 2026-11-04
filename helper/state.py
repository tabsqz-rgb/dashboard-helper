"""The helper's memory (TikTok logins, campaigns, what's been submitted), kept encrypted so it can live in a public repo."""
import json
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

PATH = Path(__file__).resolve().parent.parent / "state.enc"


def new_key():
    return Fernet.generate_key().decode()


def load(key, path=PATH):
    """The saved state, or {} if there isn't one yet. Raises ValueError if the key doesn't open it."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(Fernet(key.encode()).decrypt(path.read_bytes()))
    except InvalidToken as e:
        raise ValueError("The state key doesn't match the saved state") from e


def save(data, key, path=PATH):
    Path(path).write_bytes(Fernet(key.encode()).encrypt(json.dumps(data).encode()))
