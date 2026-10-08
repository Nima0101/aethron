import hmac
import os
import re
import stat
from pathlib import Path


class Auth:
    def __init__(self, credentials):
        self.tokens = []
        for credential in credentials:
            path = Path(credential.token_file)
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or (
                os.name != "nt" and (info.st_mode & 0o077 or info.st_uid != os.getuid())
            ):
                raise ValueError("invalid_credentials")
            token = path.read_text().strip()
            if not re.fullmatch("[a-f0-9]{64}", token):
                raise ValueError("invalid_credentials")
            self.tokens.append((token, credential.principal))

    def authenticate(self, header):
        if not header or not header.startswith("Bearer "):
            return None
        token = header[7:]
        if not re.fullmatch("[a-f0-9]{64}", token):
            return None
        for expected, principal in self.tokens:
            if hmac.compare_digest(token, expected):
                return principal
        return None
