from backend.ai.learner_model import LearnerState


learner = LearnerState(student_id=1)

topic = "ATP synthase"

print("Initial mastery:")
print(learner.get_mastery(topic))


print("\nAfter correct answer:")
print(learner.update_mastery(topic, True))


print("\nAfter another correct answer:")
print(learner.update_mastery(topic, True))


print("\nAfter incorrect answer:")
print(learner.update_mastery(topic, False))


print("\nFinal mastery:")
print(learner.get_mastery(topic))

print("\nDifficulty:")
print(learner.get_difficulty(topic))

print("\n--- Adaptive Difficulty Test ---")

learner = LearnerState(student_id=1)

print("Initial:", learner.get_difficulty(topic))

for _ in range(2):
    learner.update_mastery(topic, True)

print("After 2 correct:", learner.get_mastery(topic))
print("Difficulty:", learner.get_difficulty(topic))

for _ in range(2):
    learner.update_mastery(topic, True)

print("After 4 correct:", learner.get_mastery(topic))
print("Difficulty:", learner.get_difficulty(topic))

for _ in range(1):
    learner.update_mastery(topic, True)

print("After 5 correct:", learner.get_mastery(topic))
print("Difficulty:", learner.get_difficulty(topic))

print("\n--- Weakest Topic Test ---")

learner = LearnerState(student_id=1)

topics = [
    "ATP synthase",
    "Electron transport chain",
    "Chemiosmosis"
]

# ATP synthase → strong
for _ in range(4):
    learner.update_mastery("ATP synthase", True)

# Electron transport chain → medium
for _ in range(2):
    learner.update_mastery("Electron transport chain", True)

# Chemiosmosis → weak
learner.update_mastery("Chemiosmosis", False)

print("\nTopic Mastery:")

for topic_name in topics:
    print(
        topic_name,
        ":",
        learner.get_mastery(topic_name)
    )

print("\nWeakest Topic:")
print(learner.get_weakest_topic())