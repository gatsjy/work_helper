from pathlib import Path
import secrets

# 프로젝트 루트의 .secret.key
KEY_FILE = Path(__file__).resolve().parent.parent / ".secret.key"


def get_secret_key():
    """
    .secret.key 파일을 읽어온다.
    없으면 256bit 랜덤 키를 생성하여 저장한다.
    """

    if not KEY_FILE.exists():

        secret = secrets.token_hex(32)   # 32byte = 256bit

        KEY_FILE.write_text(
            secret,
            encoding="utf-8"
        )

        print(">> New secret key generated.")

    else:

        secret = KEY_FILE.read_text(
            encoding="utf-8"
        ).strip()

    return secret