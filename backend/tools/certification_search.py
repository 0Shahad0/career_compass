import hashlib
import io
import json
import logging
import os
import re
import time
import unicodedata
import uuid
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from urllib.parse import quote

import certifi
import numpy as np
import requests
from openai import OpenAI

from backend.config import settings


BASE_DATA_URL = (
    "https://raw.githubusercontent.com/hans6883/cert-atlas/master/data"
)
INDEX_URL = f"{BASE_DATA_URL}/index.json"
REQUEST_TIMEOUT = (10, 30)  # (connect_timeout, read_timeout) — covers SSL handshake

EMBEDDING_MODEL = "text-embedding-3-small"
TOP_K = 40
EMBEDDING_BATCH_SIZE = 32
TEXT_CHUNK_BYTES = 6000
INDEX_VERSION = 2

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEMANTIC_INDEX_DIR = PROJECT_ROOT / "data" / "certifications"
BLUEPRINT_CACHE_DIR = SEMANTIC_INDEX_DIR / "blueprints"
MANIFEST_PATH = SEMANTIC_INDEX_DIR / "manifest.json"

logger = logging.getLogger(__name__)
_build_lock = RLock()


def _normalize(value: object) -> str:
    if not isinstance(value, str):
        return ""

    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.replace("–", "-").replace("—", "-")

    return re.sub(r"\s+", " ", value).strip()


def _get_json(url: str) -> dict:
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT, verify=certifi.where())
    except requests.exceptions.ConnectTimeout:
        raise requests.RequestException(
            f"Connection to {url} timed out (SSL/TCP handshake). "
            "Check your internet connection or proxy settings."
        )
    response.raise_for_status()

    data = response.json()

    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object from {url}")

    return data


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None

    try:
        with NamedTemporaryFile(
            dir=path.parent,
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary = Path(file.name)
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())

        # On Windows, antivirus (e.g. Defender) briefly locks newly created
        # temp files, causing os.replace() to raise PermissionError (WinError 5).
        # Retry with exponential backoff to ride out the lock window.
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                temporary = None  # rename succeeded — don't delete in finally
                return
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.05 * (2 ** attempt))  # 50ms, 100ms, 200ms, 400ms, 800ms

    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@lru_cache(maxsize=1)
def load_certifications() -> list[dict]:
    """Load the full catalog; malformed non-object entries are ignored."""
    exams = _get_json(INDEX_URL).get("exams")

    if not isinstance(exams, list):
        raise ValueError("Cert Atlas index must contain an exams list.")

    valid = []

    for position, exam in enumerate(exams):
        if isinstance(exam, dict):
            valid.append(exam)
        else:
            logger.warning(
                "Ignoring malformed catalog entry at position %s",
                position,
            )

    return valid


def refresh_certifications() -> None:
    """Clear memory caches. Use force_refresh=True to refresh persisted data."""
    with _build_lock:
        load_certifications.cache_clear()
        _read_generation.cache_clear()


def _is_retired(exam: dict) -> bool:
    return _normalize(exam.get("lifecycle_status")) == "retired"


def is_recommendation_certification(exam: object) -> bool:
    """Exclude only retired records and explicitly identified recruitment exams."""
    if not isinstance(exam, dict) or _is_retired(exam):
        return False

    credential = exam.get("credential")
    nested_type = (
        credential.get("type")
        if isinstance(credential, dict)
        else None
    )

    return not any(
        _normalize(value) == "recruitment_exam"
        for value in (
            nested_type,
            exam.get("credential_type"),
        )
    )


def _clean_exam(exam: dict) -> dict:
    fields = (
        "exam_id",
        "exam_name",
        "certification_name",
        "exam_code",
        "certifying_body",
        "vendor_slug",
        "domains",
        "total_questions",
        "duration_minutes",
        "source_url",
        "practice_url",
        "enriched",
        "lifecycle_status",
        "retires_on",
        "retired_on",
        "replacement_exam_code",
        "replacement_url",
        "credential",
        "credential_type",
        "target_audience",
        "recommended_experience",
        "prerequisites",
    )

    return {field: exam.get(field) for field in fields}


def get_all_certifications(
    include_retired: bool = False,
) -> list[dict]:
    """Manual catalog access; recruitment exams remain available."""
    return [
        _clean_exam(exam)
        for exam in load_certifications()
        if include_retired or not _is_retired(exam)
    ]


def search_certifications(
    query: str,
    include_retired: bool = False,
) -> list[dict]:
    """Search manually by ID, code, name, certification name, or provider."""
    value = _normalize(query)

    if not value:
        return []

    matches = []

    for exam in get_all_certifications(include_retired):
        exam_id, code, name, certification_name, provider = (
            _normalize(exam.get(key))
            for key in (
                "exam_id",
                "exam_code",
                "exam_name",
                "certification_name",
                "certifying_body",
            )
        )

        searchable = " ".join(
            (
                exam_id,
                code,
                name,
                certification_name,
                provider,
            )
        )

        if value == exam_id:
            score = 100
        elif value == code:
            score = 95
        elif value in (name, certification_name):
            score = 90
        elif value in name or value in certification_name:
            score = 70
        elif value in code:
            score = 65
        elif value in provider:
            score = 50
        elif all(word in searchable for word in value.split()):
            score = 30
        else:
            continue

        matches.append((score, exam))

    matches.sort(
        key=lambda item: (
            -item[0],
            _normalize(item[1].get("exam_name")),
        )
    )

    return [exam for _, exam in matches]


def find_certification(
    identifier: str,
    include_retired: bool = True,
) -> dict | None:
    """Resolve one certification by an exact ID, code, or name.

    Provider lookup belongs exclusively to search_certifications().
    Ambiguous matches return None.
    """
    value = _normalize(identifier)

    if not value:
        return None

    exams = get_all_certifications(include_retired)

    for keys in (
        ("exam_id",),
        ("exam_code",),
        ("exam_name", "certification_name"),
    ):
        matches = [
            exam
            for exam in exams
            if any(
                _normalize(exam.get(key)) == value
                for key in keys
            )
        ]

        if len(matches) == 1:
            return matches[0]

        if matches:
            return None

    return None


def _blueprint_cache_path(exam_id: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", exam_id)[:80]
    digest = _sha256(exam_id.encode("utf-8"))

    return BLUEPRINT_CACHE_DIR / f"{safe_name}-{digest}.json"


def _valid_blueprint(data: object, exam_id: str) -> bool:
    return (
        isinstance(data, dict)
        and data.get("exam_id") == exam_id
        and bool(_normalize(data.get("exam_name")))
    )


def _cached_blueprint(exam_id: str) -> dict | None:
    try:
        data = json.loads(
            _blueprint_cache_path(exam_id).read_bytes()
        )

        if _valid_blueprint(data, exam_id):
            return data

    except (
        OSError,
        ValueError,
        UnicodeError,
        RecursionError,
    ):
        pass

    return None


def get_certification_blueprint(
    identifier: str,
    force_refresh: bool = False,
) -> dict | None:
    """Load a blueprint from its persistent cache or Cert Atlas."""
    if not isinstance(identifier, str) or not identifier.strip():
        return None

    # Exact exam IDs can be served offline without loading the catalog.
    if not force_refresh:
        cached = _cached_blueprint(identifier)

        if cached is not None:
            return cached

    exam = find_certification(identifier)

    if exam is None:
        return None

    exam_id = exam.get("exam_id")
    vendor = exam.get("vendor_slug")

    if not all(
        isinstance(value, str)
        and value.strip()
        and value not in (".", "..")
        for value in (exam_id, vendor)
    ):
        return None

    if not force_refresh:
        cached = _cached_blueprint(exam_id)

        if cached is not None:
            return cached

    url = (
        f"{BASE_DATA_URL}/{quote(vendor, safe='')}/"
        f"{quote(exam_id, safe='')}.json"
    )

    blueprint = _get_json(url)

    if not _valid_blueprint(blueprint, exam_id):
        raise ValueError(f"Invalid blueprint for {exam_id}")

    try:
        _atomic_write(
            _blueprint_cache_path(exam_id),
            _json_bytes(blueprint),
        )
    except OSError:
        logger.warning(
            "Could not cache blueprint %s",
            exam_id,
            exc_info=True,
        )

    return blueprint


def _text(value: object, depth: int = 0) -> str:
    """Extract descriptive text without stringifying arbitrary dictionaries."""
    if depth > 20:
        return ""

    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()

    if isinstance(value, (list, tuple)):
        return "; ".join(
            part
            for item in value
            if (part := _text(item, depth + 1))
        )

    if isinstance(value, dict):
        return "; ".join(
            part
            for key in ("description", "title", "name")
            if (part := _text(value.get(key), depth + 1))
        )

    return ""


def _prerequisites_to_text(prerequisites: object) -> str:
    return _text(prerequisites)


def _rich_domains_to_text(
    domains: object,
    depth: int = 0,
) -> str:
    if depth > 20:
        return ""

    if isinstance(domains, str):
        return _text(domains)

    if isinstance(domains, (list, tuple)):
        return "\n".join(
            part
            for item in domains
            if (
                part := _rich_domains_to_text(
                    item,
                    depth + 1,
                )
            )
        )

    if not isinstance(domains, dict):
        return ""

    parts = []

    for key in (
        "name",
        "domain_name",
        "domain",
        "title",
        "description",
    ):
        value = _text(domains.get(key))

        if value:
            parts.append(value)

    for key in (
        "objectives",
        "sub_objectives",
        "subobjectives",
        "sub-objectives",
    ):
        value = _rich_domains_to_text(
            domains.get(key),
            depth + 1,
        )

        if value:
            parts.append(value)

    return "\n".join(dict.fromkeys(parts))


def build_rich_certification_text(blueprint: dict) -> str:
    """Build embedding text using professional context and exam content."""
    if not isinstance(blueprint, dict):
        return ""

    sections = []

    for label, key in (
        ("Certification", "exam_name"),
        ("Certification name", "certification_name"),
        ("Exam code", "exam_code"),
        ("Provider", "certifying_body"),
        ("Target audience", "target_audience"),
        ("Recommended experience", "recommended_experience"),
    ):
        value = _text(blueprint.get(key))

        if value:
            sections.append(f"{label}: {value}")

    for label, value in (
        (
            "Prerequisites",
            _prerequisites_to_text(blueprint.get("prerequisites")),
        ),
        (
            "Exam content",
            _rich_domains_to_text(blueprint.get("domains")),
        ),
    ):
        if value:
            sections.append(f"{label}:\n{value}")

    return "\n\n".join(sections)


def get_required_prerequisites(blueprint: dict) -> list[dict]:
    """Return explicitly required prerequisites without evaluating the user."""
    if not isinstance(blueprint, dict):
        return []

    prerequisites = blueprint.get("prerequisites")

    if not isinstance(prerequisites, list):
        return []

    return [
        {
            "type": (
                item.get("prerequisite_type")
                or item.get("type")
            ),
            "description": item.get("description"),
        }
        for item in prerequisites
        if (
            isinstance(item, dict)
            and item.get("is_required") is True
        )
    ]


@lru_cache(maxsize=1)
def _embedding_client() -> OpenAI:
    # Manual search and cache-only operations do not initialize an API client.
    return OpenAI(api_key=settings.openai_api_key)


def _normalize_vectors(vectors: object) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=np.float32)

    if (
        matrix.ndim != 2
        or not matrix.shape[0]
        or not matrix.shape[1]
    ):
        raise ValueError("Expected a nonempty embedding matrix.")

    if not np.isfinite(matrix).all():
        raise ValueError(
            "Embedding matrix contains nonfinite values."
        )

    norms = np.linalg.norm(
        matrix,
        axis=1,
        keepdims=True,
    )

    if not np.isfinite(norms).all() or np.any(norms <= 0):
        raise ValueError(
            "Embedding matrix contains invalid or zero vectors."
        )

    return matrix / norms


def _embed_texts(texts: list[str]) -> np.ndarray:
    """Embed bounded text inputs in batches and normalize their vectors."""
    if not texts or any(
        not isinstance(text, str) or not text.strip()
        for text in texts
    ):
        raise ValueError(
            "Embedding inputs must be nonempty strings."
        )

    vectors = []

    for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[start:start + EMBEDDING_BATCH_SIZE]

        response = _embedding_client().embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )

        ordered = sorted(
            response.data,
            key=lambda item: item.index,
        )

        if [item.index for item in ordered] != list(range(len(batch))):
            raise ValueError(
                "Embedding response does not match the input batch."
            )

        vectors.extend(item.embedding for item in ordered)

    return _normalize_vectors(vectors)


def _text_chunks(text: str) -> list[str]:
    """Split text without truncation or splitting a Unicode character."""
    # Conservative UTF-8 byte bound avoids adding a tokenizer dependency.
    chunks = []
    characters = []
    size = 0

    for character in text:
        width = len(character.encode("utf-8"))

        if size + width > TEXT_CHUNK_BYTES:
            chunks.append("".join(characters))
            characters = []
            size = 0

        characters.append(character)
        size += width

    if characters:
        chunks.append("".join(characters))

    return [chunk for chunk in chunks if chunk.strip()]


def _embed_documents(texts: list[str]) -> np.ndarray:
    """Create one normalized vector per complete document.

    Both certification text and full user profiles use this same approach:
    split into bounded chunks, embed all chunks, pool by chunk byte length,
    and normalize the resulting document vector.

    No document content is truncated.
    """
    chunks = []
    groups = []

    for text in texts:
        parts = _text_chunks(text)

        if not parts:
            raise ValueError("Document text is empty.")

        start = len(chunks)
        chunks.extend(parts)

        groups.append(
            (
                start,
                len(chunks),
                [len(part.encode("utf-8")) for part in parts],
            )
        )

    embedded = _embed_texts(chunks)

    vectors = [
        np.average(
            embedded[start:end],
            axis=0,
            weights=weights,
        )
        for start, end, weights in groups
    ]

    return _normalize_vectors(vectors)


def _embed_certification_texts(texts: list[str]) -> np.ndarray:
    """Create rich certification vectors through the shared document embedder."""
    return _embed_documents(texts)


@lru_cache(maxsize=1)
def _read_generation(
    generation: str,
    metadata_hash: str,
    embeddings_hash: str,
    count: int,
    dimensions: int,
) -> tuple[list[dict], np.ndarray]:
    directory = SEMANTIC_INDEX_DIR / "generations" / generation

    metadata_bytes = (directory / "metadata.json").read_bytes()
    embedding_bytes = (directory / "embeddings.npy").read_bytes()

    if (
        _sha256(metadata_bytes) != metadata_hash
        or _sha256(embedding_bytes) != embeddings_hash
    ):
        raise ValueError("Semantic index checksum mismatch.")

    metadata = json.loads(metadata_bytes)

    vectors = np.load(
        io.BytesIO(embedding_bytes),
        allow_pickle=False,
    )

    if (
        not isinstance(metadata, list)
        or len(metadata) != count
        or not isinstance(vectors, np.ndarray)
        or vectors.shape != (count, dimensions)
        or vectors.dtype != np.dtype("float32")
        or not np.isfinite(vectors).all()
        or not np.allclose(
            np.linalg.norm(vectors, axis=1),
            1.0,
            atol=1e-5,
        )
    ):
        raise ValueError(
            "Invalid semantic index structure or vectors."
        )

    seen = set()

    for item in metadata:
        if (
            not isinstance(item, dict)
            or not _normalize(item.get("exam_id"))
            or not _text(item.get("_searchable_text"))
            or not is_recommendation_certification(item)
        ):
            raise ValueError("Invalid semantic index metadata.")

        if item["exam_id"] in seen:
            raise ValueError(
                "Duplicate exam ID in semantic index."
            )

        seen.add(item["exam_id"])

    vectors.setflags(write=False)

    return metadata, vectors


def _read_index() -> tuple[list[dict], np.ndarray, dict] | None:
    try:
        manifest = json.loads(MANIFEST_PATH.read_bytes())

        if not isinstance(manifest, dict):
            raise ValueError("Invalid manifest.")

        if (
            manifest.get("index_version") != INDEX_VERSION
            or manifest.get("embedding_model") != EMBEDDING_MODEL
            or manifest.get("source_url") != INDEX_URL
            or manifest.get("chunk_bytes") != TEXT_CHUNK_BYTES
        ):
            return None

        generation = manifest.get("generation")
        count = manifest.get("certification_count")
        dimensions = manifest.get("dimensions")

        if (
            not isinstance(generation, str)
            or not re.fullmatch(r"[0-9a-f]{32}", generation)
            or type(count) is not int
            or count <= 0
            or type(dimensions) is not int
            or dimensions <= 0
            or type(manifest.get("complete")) is not bool
            or not isinstance(manifest.get("skipped"), list)
        ):
            raise ValueError("Invalid manifest fields.")

        metadata, vectors = _read_generation(
            generation,
            manifest["metadata_sha256"],
            manifest["embeddings_sha256"],
            count,
            dimensions,
        )

        return metadata, vectors, manifest

    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        EOFError,
        RecursionError,
    ):
        logger.warning(
            "Semantic cache unavailable or invalid; rebuild needed."
        )
        return None


def _build_result(manifest: dict, status: str) -> dict:
    return {
        "status": status,
        "count": manifest["certification_count"],
        "embedding_model": EMBEDDING_MODEL,
        "complete": manifest["complete"],
        "skipped": manifest["skipped"],
        "generation": manifest["generation"],
    }


def build_semantic_index(
    force_refresh: bool = False,
    *,
    force: bool | None = None,
) -> dict:
    """Build an index containing all valid recommendation certifications.

    A complete local snapshot is reused without network calls unless a
    source refresh is requested.

    force_refresh=True refreshes the catalog and blueprints, rebuilds rich
    text, and reuses existing embeddings wherever that text is unchanged.

    New or changed text is embedded. Removed, excluded, or invalid records
    are not carried into the new snapshot.

    Explicit builds retry previously skipped records.

    The legacy force keyword remains supported as a source-refresh alias.
    """
    force_refresh = bool(force_refresh or force)

    with _build_lock:
        existing = _read_index()

        if (
            existing is not None
            and not force_refresh
            and existing[2]["complete"]
        ):
            return _build_result(existing[2], "existing")

        # Preserve the previous valid vectors even during source refresh.
        # Model, index version, and chunk settings were checked by _read_index().
        previous = {}

        if existing is not None:
            previous = {
                item["exam_id"]: (
                    item["_searchable_text"],
                    vector,
                )
                for item, vector in zip(
                    existing[0],
                    existing[1],
                )
            }

        if force_refresh:
            load_certifications.cache_clear()

        metadata = []
        skipped = []
        seen = set()

        # Always inspect the complete current catalog.
        for exam in load_certifications():
            if not is_recommendation_certification(exam):
                continue

            exam_id = exam.get("exam_id")

            if not isinstance(exam_id, str) or not exam_id.strip():
                skipped.append(
                    {
                        "exam_id": None,
                        "reason": "Missing valid exam_id",
                    }
                )
                continue

            if exam_id in seen:
                logger.warning(
                    "Ignoring duplicate catalog exam ID %s",
                    exam_id,
                )
                continue

            try:
                blueprint = get_certification_blueprint(
                    exam_id,
                    force_refresh=force_refresh,
                )

                if blueprint is None:
                    raise ValueError("Blueprint unavailable")

                if not is_recommendation_certification(blueprint):
                    seen.add(exam_id)
                    continue

                combined = {**exam, **blueprint}

                for key in (
                    "exam_name",
                    "exam_code",
                    "certifying_body",
                ):
                    if not _text(combined.get(key)):
                        combined[key] = exam.get(key)

                rich_text = build_rich_certification_text(combined)

                if not rich_text:
                    raise ValueError(
                        "Empty rich certification text"
                    )

                item = _clean_exam(combined)
                item["_searchable_text"] = rich_text

                metadata.append(item)
                seen.add(exam_id)

            except (
                requests.RequestException,
                ValueError,
                TypeError,
                OSError,
                UnicodeError,
                RecursionError,
            ) as exc:
                skipped.append(
                    {
                        "exam_id": exam_id,
                        "reason": str(exc),
                    }
                )

                logger.warning(
                    "Skipping %s: %s",
                    exam_id,
                    exc,
                )

        if not metadata:
            raise ValueError(
                "No valid recommendation blueprints; index not replaced."
            )

        metadata.sort(key=lambda item: item["exam_id"])

        vectors = [None] * len(metadata)
        pending = []

        for position, item in enumerate(metadata):
            old = previous.get(item["exam_id"])

            if (
                old is not None
                and old[0] == item["_searchable_text"]
            ):
                # Reuse unchanged embeddings, including on weekly refresh.
                vectors[position] = old[1]
            else:
                pending.append(position)

        if pending:
            # Only new or changed certification text reaches the embedding API.
            # Service failures abort publication and preserve the old snapshot.
            generated = _embed_certification_texts(
                [
                    metadata[position]["_searchable_text"]
                    for position in pending
                ]
            )

            for position, vector in zip(pending, generated):
                vectors[position] = vector

        matrix = _normalize_vectors(vectors)

        # Publish immutable files first, then atomically switch the manifest.
        # Readers cannot mix metadata and embeddings from different builds.
        generation = uuid.uuid4().hex
        directory = (
            SEMANTIC_INDEX_DIR
            / "generations"
            / generation
        )

        metadata_bytes = _json_bytes(metadata)

        buffer = io.BytesIO()
        np.save(
            buffer,
            matrix,
            allow_pickle=False,
        )
        embedding_bytes = buffer.getvalue()

        manifest = {
            "index_version": INDEX_VERSION,
            "embedding_model": EMBEDDING_MODEL,
            "source_url": INDEX_URL,
            "chunk_bytes": TEXT_CHUNK_BYTES,
            "generation": generation,
            "certification_count": len(metadata),
            "dimensions": matrix.shape[1],
            "metadata_sha256": _sha256(metadata_bytes),
            "embeddings_sha256": _sha256(embedding_bytes),
            "complete": not skipped,
            "skipped": skipped,
        }

        _atomic_write(
            directory / "metadata.json",
            metadata_bytes,
        )
        _atomic_write(
            directory / "embeddings.npy",
            embedding_bytes,
        )
        _atomic_write(
            MANIFEST_PATH,
            _json_bytes(manifest),
        )

        _read_generation.cache_clear()

        return _build_result(manifest, "built")


def _load_semantic_index() -> tuple[list[dict], np.ndarray]:
    with _build_lock:
        snapshot = _read_index()

        if snapshot is None:
            build_semantic_index()
            snapshot = _read_index()

        if snapshot is None:
            raise RuntimeError(
                "Could not load the semantic index."
            )

        if not snapshot[2]["complete"]:
            logger.warning(
                "Using partial index: %s records skipped. "
                "Run build_semantic_index() explicitly to retry.",
                len(snapshot[2]["skipped"]),
            )

        return snapshot[0], snapshot[1]


def rebuild_semantic_index() -> dict:
    """Refresh source data while reusing unchanged certification embeddings."""
    return build_semantic_index(force_refresh=True)


def semantic_search_certifications(
    profile_text: str,
    top_k: int = TOP_K,
) -> list[dict]:
    """Rank all indexed certifications against the full professional profile.

    Long profiles use the same chunk-and-pool embedding approach as
    certifications. Retrieval uses only cosine similarity between the
    resulting normalized document vectors.
    """
    if not isinstance(profile_text, str):
        raise TypeError("profile_text must be a string.")

    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise TypeError("top_k must be an integer.")

    if not profile_text.strip() or top_k <= 0:
        return []

    certifications, vectors = _load_semantic_index()

    # Embed the entire profile without truncation. Long CVs produce multiple
    # bounded chunk embeddings, pooled into one normalized profile vector.
    query_vector = _embed_documents([profile_text])[0]

    if vectors.shape[1] != query_vector.shape[0]:
        raise ValueError(
            "Embedding dimensions changed; rebuild the semantic index."
        )

    # Both sides are normalized, so the dot product is cosine similarity.
    # Score ALL certifications, sort ALL scores, and only then apply Top K.
    similarities = vectors @ query_vector
    ranked_indices = np.argsort(
        -similarities,
        kind="stable",
    )

    return [
        {
            **certifications[int(index)],
            "_retrieval_score": float(similarities[int(index)]),
        }
        for index in ranked_indices[:top_k]
    ]