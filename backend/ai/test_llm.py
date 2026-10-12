from backend.ai.llm import LLM


llm = LLM()


prompt = """
Explain what ATP synthase does in three sentences.
"""


answer = llm.generate(prompt)


print("\nLLM RESPONSE")
print("=" * 60)
print(answer)