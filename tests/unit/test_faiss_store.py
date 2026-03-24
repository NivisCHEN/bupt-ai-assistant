"""Tests for the FAISS vector store."""

import os

import numpy as np
import pytest

from src.retriever.faiss_store import FAISSStore


@pytest.fixture()
def store():
    return FAISSStore(dimension=64)


@pytest.fixture()
def random_vectors():
    """Generate 100 random 64-d vectors, L2-normalized."""
    rng = np.random.RandomState(42)
    vecs = rng.randn(100, 64).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / norms


class TestBuildIndex:

    def test_build_flat_index(self, store, random_vectors):
        store.build_index(random_vectors, use_ivf=False)
        assert store.size == 100

    def test_build_index_empty(self, store):
        empty = np.empty((0, 64), dtype=np.float32)
        store.build_index(empty)
        assert store.size == 0

    def test_build_flat_index_small_dataset(self, store, random_vectors):
        # With use_ivf=True but fewer than 10k vectors -> should fall back to flat
        store.build_index(random_vectors, use_ivf=True)
        assert store.size == 100


class TestSearch:

    def test_search_returns_results(self, store, random_vectors):
        store.build_index(random_vectors, use_ivf=False)
        query = random_vectors[0:1]
        distances, indices = store.search(query, top_k=5)
        assert distances.shape[1] == 5
        assert indices.shape[1] == 5
        # The query itself should be the top match
        assert indices[0, 0] == 0

    def test_search_top_k_exceeds_size(self, store, random_vectors):
        store.build_index(random_vectors[:5], use_ivf=False)
        query = random_vectors[0:1]
        distances, indices = store.search(query, top_k=20)
        assert indices.shape[1] == 5  # clamped to available vectors

    def test_search_empty_index(self, store):
        distances, indices = store.search(np.zeros((1, 64), dtype=np.float32), top_k=5)
        assert distances.shape[1] == 0
        assert indices.shape[1] == 0

    def test_search_no_index(self, store):
        # No index built at all
        distances, indices = store.search(np.zeros((1, 64), dtype=np.float32))
        assert indices.shape[1] == 0

    def test_search_1d_query(self, store, random_vectors):
        store.build_index(random_vectors, use_ivf=False)
        query = random_vectors[0]  # shape (64,) instead of (1, 64)
        distances, indices = store.search(query, top_k=3)
        assert indices.shape == (1, 3)


class TestSaveLoad:

    def test_save_and_load(self, store, random_vectors, tmp_path):
        store.build_index(random_vectors, use_ivf=False)
        path = str(tmp_path / "test.index")
        store.save_index(path)
        assert os.path.exists(path)

        new_store = FAISSStore(dimension=64)
        new_store.load_index(path)
        assert new_store.size == 100

        # Search results should be identical
        query = random_vectors[0:1]
        d1, i1 = store.search(query, top_k=5)
        d2, i2 = new_store.search(query, top_k=5)
        np.testing.assert_array_equal(i1, i2)

    def test_save_without_index_raises(self, store):
        with pytest.raises(RuntimeError):
            store.save_index("/tmp/nonexistent.index")

    def test_load_nonexistent_raises(self, store):
        with pytest.raises(FileNotFoundError):
            store.load_index("/tmp/this_file_does_not_exist.index")

    def test_save_creates_parent_dirs(self, store, random_vectors, tmp_path):
        store.build_index(random_vectors[:10], use_ivf=False)
        path = str(tmp_path / "nested" / "dir" / "index.faiss")
        store.save_index(path)
        assert os.path.exists(path)


class TestAddVectors:

    def test_add_to_existing_index(self, store, random_vectors):
        store.build_index(random_vectors[:50], use_ivf=False)
        assert store.size == 50
        store.add_vectors(random_vectors[50:])
        assert store.size == 100

    def test_add_creates_index_if_none(self, store, random_vectors):
        store.add_vectors(random_vectors[:10])
        assert store.size == 10

    def test_add_empty_vectors(self, store, random_vectors):
        store.build_index(random_vectors[:10], use_ivf=False)
        store.add_vectors(np.empty((0, 64), dtype=np.float32))
        assert store.size == 10  # unchanged


class TestProperties:

    def test_size_no_index(self, store):
        assert store.size == 0

    def test_dimension(self, store):
        assert store.dimension == 64
