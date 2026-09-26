"""
Kalıcı vektör hafıza.
- Yazma: her konuşma turu otomatik olarak burada saklanır (chroma_data/ klasörüne, diske).
- Okuma: SADECE model <CALL_TOOL: search_memory ...|> ürettiğinde tetiklenir.
Embedding modeli chat modelinden ayrıdır - küçük ve hızlıdır (nomic-embed-text).
"""
import ollama
import chromadb

EMBED_MODEL = "nomic-embed-text"
COLLECTION_NAME = "sentinel_memory"


class MemoryStore:
    def __init__(self, persist_path="./chroma_data", ollama_client=None):
        self.client = chromadb.PersistentClient(path=persist_path)
        self.collection = self.client.get_or_create_collection(COLLECTION_NAME)
        self._next_id = self.collection.count()
        # main.py'nin bulduğu host'a bağlı client geçilmezse, modül seviyesindeki
        # varsayılana (OLLAMA_HOST env değişkeni / 127.0.0.1) düşer - WSL'de bu
        # genelde başarısız olur, bu yüzden main.py her zaman kendi client'ını geçmeli.
        self.ollama_client = ollama_client if ollama_client is not None else ollama

    def _embed(self, text: str) -> list[float]:
        result = self.ollama_client.embed(model=EMBED_MODEL, input=text)
        return result["embeddings"][0]

    def add(self, text: str, role: str):
        """Her konuşma satırını kalıcı hafızaya yazar."""
        vector = self._embed(text)
        self.collection.add(
            ids=[str(self._next_id)],
            embeddings=[vector],
            documents=[text],
            metadatas=[{"role": role}],
        )
        self._next_id += 1

    def search(self, query: str, top_k: int = 5) -> list[str]:
        """Model bir sorguyla hafızaya baktığında çağrılır."""
        if self.collection.count() == 0:
            return []
        vector = self._embed(query)
        results = self.collection.query(query_embeddings=[vector], n_results=top_k)
        return results["documents"][0]