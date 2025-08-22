from __future__ import annotations

from .app import create_app


def main() -> None:
    app = create_app()
    # Default dev server
    app.run(host="127.0.0.1", port=5000, debug=True)


if __name__ == "__main__":
    main()
