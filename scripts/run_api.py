#!/usr/bin/env python3
from __future__ import annotations

import uvicorn


if __name__ == "__main__":
    uvicorn.run("browserdelta.main:app", app_dir="backend", host="127.0.0.1", port=8000, reload=True)
