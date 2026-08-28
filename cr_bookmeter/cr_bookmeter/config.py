import os

from dotenv import dotenv_values


def get_user_id(env_file="./env/.env"):
    """環境変数を優先し、未指定の場合は .env から USER_ID を取得する。"""
    user_id = os.environ.get("USER_ID")
    if user_id is None:
        user_id = dotenv_values(env_file).get("USER_ID")

    if not user_id:
        raise ValueError(
            "USER_ID が環境変数または .env ファイルに定義されていません。"
        )
    return user_id
