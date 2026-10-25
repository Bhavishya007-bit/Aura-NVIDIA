"""One worker per persistent volume; PostgreSQL coordinates background work."""

import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.production.app:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        workers=1,
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("AURA_TRUSTED_PROXY_IPS", "127.0.0.1"),
    )
