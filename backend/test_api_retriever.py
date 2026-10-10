from backend.ai.embeddings import EmbeddingModel
from backend.ai.pg_retrieval import PostgresRetriever


def main():
    embedding_model = EmbeddingModel()
    retriever = PostgresRetriever(embedding_model)

    query = "How does ATP synthase produce ATP?"

    results = retriever.search(
        query=query,
        top_k=3
    )

    print(f"\nQuery: {query}")
    print(f"Results found: {len(results)}")

    for result in results:
        print("\n-------------------------")
        print(f"Score: {result.score:.4f}")
        print(f"Chunk ID: {result.chunk.chunk_id}")
        print(f"Source: {result.chunk.source_name}")
        print(f"Page: {result.chunk.page}")
        print(f"Topic: {result.chunk.topic}")
        print(f"Content: {result.chunk.content}")


if __name__ == "__main__":
    main()