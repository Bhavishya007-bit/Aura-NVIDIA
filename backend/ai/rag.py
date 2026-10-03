from backend.ai.retrieval import Retriever
from backend.ai.llm import LLM


class RAG:

    def __init__(
        self,
        retriever: Retriever,
        llm: LLM
    ):
        self.retriever = retriever
        self.llm = llm

    def answer(
        self,
        question: str,
        top_k: int = 3
    ) -> dict:

        # Step 1: Check whether the question
        # is relevant to the uploaded material.
        if not self.retriever.is_relevant(question):

            return {
                "answer": (
                    "I couldn't find enough information about this "
                    "in the uploaded material."
                ),
                "sources": []
            }

        # Step 2: Retrieve relevant chunks.
        results = self.retriever.search(
            question,
            top_k=top_k
        )

        # Safety check.
        if not results:

            return {
                "answer": (
                    "I couldn't find enough information about this "
                    "in the uploaded material."
                ),
                "sources": []
            }

        # Step 3: Build context for the LLM.
        context_parts = []

        for i, result in enumerate(results, start=1):

            chunk = result.chunk
            score = result.chunk

            source = (
                f"Source {i}\n"
                f"Content:\n"
                f"{chunk.content}"
            )

            context_parts.append(source)

        context = "\n\n".join(context_parts)

        # Step 4: Build grounded prompt.
        prompt = f"""
You are an AI study tutor.

Answer the student's question using ONLY the provided
course material.

Do not use outside knowledge.

If the provided material does not contain enough information
to answer the question, clearly say:

"I couldn't find enough information about this in the
uploaded material."

COURSE MATERIAL:
----------------
{context}
----------------

STUDENT QUESTION:
{question}

Give a clear and concise answer.

Do not create, invent, or mention page numbers,
timestamps, file names, or citations.
"""

        # Step 5: Generate answer.
        answer = self.llm.generate(prompt)

        # Step 6: Python creates the citations.
        # The LLM does NOT control citation metadata.
        sources = []

        for result in results:

            chunk = result.chunk

            sources.append({
                "chunk_id": chunk.chunk_id,
                "source_id": chunk.source_id,
                "source_name": chunk.source_name,
                "source_type": chunk.source_type,
                "page": chunk.page,
                "slide": chunk.slide,
                "timestamp_start": chunk.timestamp_start,
                "timestamp_end": chunk.timestamp_end,
                "score": float(result.score)
            })

        return {
            "answer": answer,
            "sources": sources
        }