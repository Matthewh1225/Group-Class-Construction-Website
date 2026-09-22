import os
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

load_dotenv()

#"memory://" used for localHost
limiter=Limiter(
    key_func=get_remote_address,
    storage_uri=os.getenv(
    "RATELIMIT_STORAGE_URI",
        "memory://"
    ),
    headers_enabled=True,
    #improves time winmdow for ratelimit
    strategy="moving-window",
)