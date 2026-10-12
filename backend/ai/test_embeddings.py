from backend.ai.embeddings import EmbeddingModel


embedding_model = EmbeddingModel()


text = """
ATP synthase is an important enzyme involved in oxidative phosphorylation.
It uses the proton gradient across the inner mitochondrial membrane.
"""


embedding = embedding_model.embed_documents([text])


print("Embedding type:", type(embedding))
print("Embedding shape:", embedding.shape)
print("First 10 values:", embedding[0][:10])