"""
LINE Rich Menu のセットアップスクリプト。

使い方:
    python scripts/setup_rich_menu.py

環境変数:
    LINE_CHANNEL_ACCESS_TOKEN   Messaging API チャネルアクセストークン
    LIFF_ID                     LIFF アプリのID (liff.ai/ 以降の ID)

実行前に .env を読み込むか、環境変数を直接設定すること。
"""

import json
import os
import sys
import textwrap
from pathlib import Path

import httpx

BASE = "https://api.line.me/v2/bot"


def _headers() -> dict[str, str]:
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        sys.exit("ERROR: LINE_CHANNEL_ACCESS_TOKEN is not set")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _liff_id() -> str:
    lid = os.environ.get("LIFF_ID")
    if not lid:
        sys.exit("ERROR: LIFF_ID is not set")
    return lid


def delete_all_rich_menus(client: httpx.Client) -> None:
    resp = client.get(f"{BASE}/richmenu/list", headers=_headers())
    resp.raise_for_status()
    menus = resp.json().get("richmenus", [])
    for m in menus:
        mid = m["richMenuId"]
        client.delete(f"{BASE}/richmenu/{mid}", headers=_headers()).raise_for_status()
        print(f"  deleted: {mid}")


def create_rich_menu(client: httpx.Client, liff_id: str) -> str:
    liff_url = f"https://liff.line.me/{liff_id}"

    body = {
        "size": {"width": 2500, "height": 843},
        "selected": True,
        "name": "pill-reminder-menu",
        "chatBarText": "メニュー",
        "areas": [
            # 今日の服薬 (左1/3)
            {
                "bounds": {"x": 0, "y": 0, "width": 833, "height": 843},
                "action": {
                    "type": "uri",
                    "label": "今日の服薬",
                    "uri": f"{liff_url}/",
                },
            },
            # カレンダー (中1/3)
            {
                "bounds": {"x": 833, "y": 0, "width": 834, "height": 843},
                "action": {
                    "type": "uri",
                    "label": "カレンダー",
                    "uri": f"{liff_url}/calendar",
                },
            },
            # 設定 (右1/3)
            {
                "bounds": {"x": 1667, "y": 0, "width": 833, "height": 843},
                "action": {
                    "type": "uri",
                    "label": "設定",
                    "uri": f"{liff_url}/settings",
                },
            },
        ],
    }

    resp = client.post(f"{BASE}/richmenu", headers=_headers(), json=body)
    resp.raise_for_status()
    menu_id = resp.json()["richMenuId"]
    print(f"  created: {menu_id}")
    return menu_id


def upload_image(client: httpx.Client, menu_id: str, image_path: Path) -> None:
    if not image_path.exists():
        print(f"  [SKIP] image not found: {image_path}")
        print("         Upload the image manually via LINE Developers console.")
        return

    headers = {
        "Authorization": _headers()["Authorization"],
        "Content-Type": "image/png",
    }
    with image_path.open("rb") as f:
        resp = client.post(
            f"https://api-data.line.me/v2/bot/richmenu/{menu_id}/content",
            headers=headers,
            content=f.read(),
        )
    resp.raise_for_status()
    print("  image uploaded")


def set_default(client: httpx.Client, menu_id: str) -> None:
    resp = client.post(
        f"{BASE}/user/all/richmenu/{menu_id}",
        headers=_headers(),
    )
    resp.raise_for_status()
    print("  set as default for all users")


def main() -> None:
    liff_id = _liff_id()
    image_path = Path(__file__).parent / "rich_menu.png"

    print("=== LINE Rich Menu Setup ===")
    with httpx.Client(timeout=30) as client:
        print("\n[1] Deleting existing rich menus ...")
        delete_all_rich_menus(client)

        print("\n[2] Creating new rich menu ...")
        menu_id = create_rich_menu(client, liff_id)

        print("\n[3] Uploading image ...")
        upload_image(client, menu_id, image_path)

        print("\n[4] Setting as default ...")
        set_default(client, menu_id)

    print(textwrap.dedent(f"""
    ===========================
    Done!  richMenuId = {menu_id}

    If you skipped the image upload:
      - Place scripts/rich_menu.png (2500×843 px, PNG, ≤1 MB)
      - Re-run this script  OR  upload manually at:
        https://developers.line.biz/console/
    ==========================="""))


if __name__ == "__main__":
    main()
