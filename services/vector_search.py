# After product edits, run python -m services.product_index to refresh search text and vectors.
# The planner worker also rebuilds missing or stale vectors when it starts.
import logging
import os
import hashlib
import tempfile
from pathlib import Path
from threading import Lock

import numpy as np
from dotenv import load_dotenv

from services import product_index, product_specs
from utils.database import database_cursor

PROJECT_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(Path(PROJECT_FOLDER) / ".env")
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
BATCH_SIZE = 64
# Each cached vector is saved with its product's text_hash. A product whose text changed, from a
# catalog edit or from a change to the text rules, no longer matches and is re-embedded.
# The cache file is committed so Render doesn't have to embed every product on each deploy.
CACHE_FILE = os.path.join(PROJECT_FOLDER, "vector_cache", "product_vectors.npz")

logger = logging.getLogger(__name__)

# Loaded once per worker and reused for every search.
model = None
cache = None               # {"ids", "vectors", "hash_by_id", "valid"} or None
cache_stamp_seen = "never"  # the cache file's modified time when this worker last looked
load_lock = Lock()         # Stop threads from loading the model at the same time.


def load_model():
    # Import here so a missing package doesn't stop the app.
    from sentence_transformers import SentenceTransformer
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return SentenceTransformer(MODEL_NAME, device=device,
                               model_kwargs={"dtype": torch.float16 if device == "cuda" else torch.float32})


def load_products():
    """Every product with the fields that feed its embedding."""
    with database_cursor() as cursor:
        return product_index.load_facts(cursor)


def read_cache_file():
    """Read the cache file. Returns None when it is missing or was built with another model."""
    if not os.path.exists(CACHE_FILE):
        return None
    with np.load(CACHE_FILE) as saved:
        if str(saved["model_name"]) != MODEL_NAME or len(saved["ids"]) != len(saved["vectors"]):
            return None
        hashes = [str(h) for h in saved["hashes"]]
        return {"ids": saved["ids"], "vectors": saved["vectors"], "hash_by_id": dict(zip(saved["ids"].tolist(), hashes))}


def build_cache(rebuild_all=False):
    """Embed new and changed products. Unchanged products keep their saved vectors."""
    products = load_products()
    old = None if rebuild_all else read_cache_file()
    old_position = {}
    if old is not None:
        old_position = {product_id: position for position, product_id in enumerate(old["ids"].tolist())}

    changed = []
    texts = []
    for product in products:
        segments = product_specs.embedding_segments_for(product)
        product["search_hash"] = product_specs.text_hash(product, segments)
        if old is None or old["hash_by_id"].get(product["product_id"]) != product["search_hash"]:
            changed.append(product)
            texts.append(". ".join(segments))

    # Keep an unchanged file so its timestamp does not make workers reload the same vectors.
    if old is not None and not changed and len(old["ids"]) == len(products):
        print(f"The vector cache is already up to date ({len(products)} products).")
        return {"products": len(products), "embedded": 0}

    new_vectors = {}
    if changed:
        embedder = load_model()
        print(f"Embedding {len(texts)} of {len(products)} products with {MODEL_NAME}...")
        # Checkpoint each chunk so a long local build can resume after interruption.
        checkpoint_folder = Path(CACHE_FILE + ".batches")
        checkpoint_folder.mkdir(exist_ok=True)
        for start in range(0, len(changed), 256):
            batch = changed[start:start + 256]
            batch_texts = texts[start:start + 256]
            digest = hashlib.sha256("\0".join([MODEL_NAME, *batch_texts]).encode()).hexdigest()
            checkpoint = checkpoint_folder / (digest + ".npy")
            if checkpoint.exists() and not rebuild_all:
                vectors = np.load(checkpoint, allow_pickle=False)
            else:
                vectors = embedder.encode(batch_texts, batch_size=BATCH_SIZE,
                                          normalize_embeddings=True, show_progress_bar=False)
                with tempfile.NamedTemporaryFile(dir=checkpoint_folder, delete=False) as saved:
                    np.save(saved, vectors)
                os.replace(saved.name, checkpoint)
            for product, vector in zip(batch, vectors):
                new_vectors[product["product_id"]] = vector
            print(f"Embedded {min(start + 256, len(changed))}/{len(changed)} products.", flush=True)

    # Keep IDs, vectors and hashes in the same order.
    ordered = []
    for product in products:
        if product["product_id"] in new_vectors:
            ordered.append(new_vectors[product["product_id"]])
        else:
            ordered.append(old["vectors"][old_position[product["product_id"]]])
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    # Save beside the real file and swap it in, so a worker never reads a half-written cache.
    temporary_file = CACHE_FILE + ".new.npz"
    np.savez(temporary_file, ids=np.array([p["product_id"] for p in products], dtype=np.int64),
             vectors=np.array(ordered, dtype=np.float32), hashes=np.array([p["search_hash"] for p in products]),
             model_name=np.array(MODEL_NAME))
    os.replace(temporary_file, CACHE_FILE)
    print(f"Saved {len(products)} product vectors ({len(changed)} embedded, {len(products) - len(changed)} reused) to {CACHE_FILE}")
    return {"products": len(products), "embedded": len(changed)}


def update_cache_if_needed():
    """Build or update the vector cache, returning False on failure so SQL search can take over.

    Read product data without changing database records.
    """
    try:
        build_cache()
    except Exception:
        logger.exception("Could not build the product vector cache; planner matching will use SQL text search only.")
        return False
    return True


def stored_hashes():
    """The search_hash saved on each product, read when the cache file is loaded."""
    with database_cursor() as cursor:
        cursor.execute("SELECT id, search_hash FROM Product")
        return {row["id"]: row["search_hash"] for row in cursor.fetchall()}


def load_vector_search():
    """Reload changed cache files without restarting, returning whether vector search is ready.

    Retry missing or unusable caches only when the file timestamp changes. A vector is only
    used when its hash matches the product's stored search_hash, so a product edited after
    the cache was built falls back to FULLTEXT until python -m services.product_index runs.
    """
    global model, cache, cache_stamp_seen

    with load_lock:
        try:
            stamp = os.path.getmtime(CACHE_FILE)
        except OSError:
            stamp = None
        if stamp == cache_stamp_seen:
            return cache is not None
        cache_stamp_seen = stamp
        cache = None

        if stamp is None:
            logger.warning("No product vector cache at %s yet. The planner worker builds it when it starts "
                           "(or run: python -m services.product_index). Until then, SQL text search is used.", CACHE_FILE)
            return False
        try:
            loaded = read_cache_file()
            if loaded is None:
                logger.warning("The product vector cache was not built with %s. The planner worker rebuilds it "
                               "when it starts (or run: python -m services.product_index).", MODEL_NAME)
                return False
            hashes = stored_hashes()
            loaded["valid"] = np.array([hashes.get(pid) == loaded["hash_by_id"][pid]
                                        for pid in loaded["ids"].tolist()], dtype=bool)
            if model is None:
                model = load_model()
        except Exception:
            logger.exception("Vector search could not start; falling back to SQL text search.")
            return False
        cache = loaded
        logger.info("Vector search ready with %s products.", len(cache["ids"]))
        return True


def search_product_ids(queries, limit):
    """Return one ranked ID list per query, using only current vectors."""
    if not load_vector_search():
        return [[] for query in queries]
    with load_lock:
        loaded = cache
        embedder = model
    if loaded is None:
        return [[] for query in queries]
    ids = loaded["ids"].tolist()
    valid = loaded["valid"]
    try:
        query_vectors = embedder.encode(queries, batch_size=BATCH_SIZE, normalize_embeddings=True)
    except Exception:
        logger.exception("Could not embed planner queries. Using FULLTEXT for this search.")
        return [[] for query in queries]

    rankings = []
    for query_vector in query_vectors:
        scores = loaded["vectors"] @ query_vector
        scores[~valid] = -np.inf
        positions = np.argsort(-scores, kind="stable")[:limit]
        rankings.append([ids[position] for position in positions if valid[position]])
    return rankings


if __name__ == "__main__":
    product_index.main()
