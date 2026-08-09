from db_adapter import build_schema_map
from intelligence.intent_engine import IntentEngine


engine = IntentEngine()
schema_map = build_schema_map()

queries = [
    "What's my DBMS attendance?",
    "Show me my AI marks.",
    "What is my timetable?",
    "Tell me my DBMS marks.",
    "How much attendance do I have in Maths?",
    "Mark Vijay absent.",
    "Show me another student's marks.",
    "What's the weather today?",
    "asdfghjkl",
]


for query in queries:
    intent = engine.parse(
        text=query,
        role="student",
        schema_map=schema_map,
    )

    print("\nQUERY:")
    print(query)

    print("INTENT:")
    print(intent)
    