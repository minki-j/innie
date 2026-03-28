from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run("server:app", host="127.0.0.1", port=8200, reload=True)
