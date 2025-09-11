import json
import os
from argparse import Namespace
from typing import Dict, Callable

from dailywire_api.dw_api.client import MiddlewareClient


def handle_show_list(args: Namespace) -> int:
    token = args.access_token or os.getenv("DAILYWIRE_ACCESS_TOKEN")
    client = MiddlewareClient(access_token=token)
    payload = client.get_show_page(slug=args.slug, membership_plan=args.membership_plan)

    # Output
    print(json.dumps(payload, ensure_ascii=False, indent=2, separators=(",", ": ")))
    return 0

CommandHandler = Callable[[Namespace], int]
HANDLERS: Dict[str, Dict[str, CommandHandler]] = {
    "show": {
        "list": handle_show_list,
    }
}