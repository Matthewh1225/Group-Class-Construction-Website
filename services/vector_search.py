# Product vector search using all-MiniLM-L6-v2.
# Rebuild the cache: python -m services.vector_search
import logging
import os
from threading import Lock

import numpy as np

from utils.database import database_cursor

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
PROJECT_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(PROJECT_FOLDER, "data", "product_vectors.npz")
MAX_DETAILS_LENGTH = 300  # Limit long product descriptions.

logger = logging.getLogger(__name__)

# Load these once and reuse them for searches.
model = None
product_ids = None      # product_ids[i] is the product for product_vectors[i]
product_vectors = None
load_attempted = False
load_lock = Lock()      # Stop threads from loading the model at the same time.


def product_text(product):
    # Put the main product details first in the search text.
    parts = [product["name"]]

    # Example: lumber / Decking.
    category = product["category"] or ""
    if product["subCategory"]:
        category = category + " / " + product["subCategory"]
    if category:
        parts.append(category)

    if product["dimensions"]:
        parts.append("Dimensions: " + product["dimensions"])
    if product["materials"]:
        parts.append("Material: " + product["materials"])

    # Put the long description last.
    if product["details"]:
        parts.append(product["details"][:MAX_DETAILS_LENGTH])

    return ". ".join(parts)


def load_model():
    # Import here so a missing package doesn't stop the app.
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME, device="cpu")


def build_cache():
    # Save each product's vector and ID.
    with database_cursor() as cursor:
        cursor.execute("SELECT id, name, category, subCategory, details, dimensions, materials"
                       " FROM Product ORDER BY id")
        products = cursor.fetchall()

    ids = []
    texts = []
    for product in products:
        ids.append(product["id"])
        texts.append(product_text(product))

    print(f"Embedding {len(texts)} products with {MODEL_NAME} on the CPU...")
    embedder = load_model()
    vectors = embedder.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=True)

    # Keep IDs and vectors in the same order.
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    np.savez(CACHE_FILE, ids=np.array(ids, dtype=np.int64), vectors=vectors.astype(np.float32),
             model_name=np.array(MODEL_NAME))
    print(f"Saved {len(ids)} product vectors to {CACHE_FILE}")


def load_vector_search():
    # Load once and return True when ready.
    global model, product_ids, product_vectors, load_attempted

    with load_lock:
        # Try once per process, even if loading fails.
        if load_attempted:
            return model is not None
        load_attempted = True

        if not os.path.exists(CACHE_FILE):
            logger.warning("No product vector cache at %s. Run: python -m services.vector_search", CACHE_FILE)
            return False

        try:
            with np.load(CACHE_FILE) as cache:
                ids = cache["ids"]
                vectors = cache["vectors"]
                cache_model = str(cache["model_name"])
            if cache_model != MODEL_NAME or len(ids) != len(vectors):
                logger.warning("The product vector cache does not match %s. Rebuild it.", MODEL_NAME)
                return False
            embedder = load_model()
        except Exception:
            logger.exception("Vector search could not start; falling back to keyword search.")
            return False

        product_ids = ids
        product_vectors = vectors
        model = embedder
        logger.info("Vector search ready with %s products.", len(product_ids))
        return True


def search_product_ids(query, limit=10):


    # Return None if vector search isn't ready.
    if not load_vector_search():
        return None

    query_vector = model.encode([query], normalize_embeddings=True)[0]
    # Compare the query with each product vector.
    scores = product_vectors @ query_vector

    # Pick the highest scores first.
    best_positions = np.argsort(-scores)[:limit]
    results = []
    for position in best_positions:
        results.append((int(product_ids[position]), float(scores[position])))
    return results


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_FOLDER, ".env"))
    build_cache()
