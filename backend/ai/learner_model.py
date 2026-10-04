from dataclasses import dataclass, field


@dataclass
class TopicState:
    """
    BKT state for a single topic.

    p_known:
        Probability that the student currently knows the topic.
    """

    p_known: float = 0.20


@dataclass
class LearnerState:
    student_id: int

    topic_states: dict[str, TopicState] = field(default_factory=dict)

    # BKT parameters
    p_guess: float = 0.20
    p_slip: float = 0.10
    p_learn: float = 0.20

    def get_topic_state(self, topic: str) -> TopicState:

        if topic not in self.topic_states:
            self.topic_states[topic] = TopicState()

        return self.topic_states[topic]

    def get_mastery(self, topic: str) -> float:

        state = self.get_topic_state(topic)

        return round(state.p_known, 2)

    def update_mastery(
        self,
        topic: str,
        correct: bool
    ) -> float:

        state = self.get_topic_state(topic)

        p_known = state.p_known

        # -----------------------------------------
        # STEP 1: Calculate observation probabilities
        # -----------------------------------------

        p_correct = (
            p_known * (1 - self.p_slip)
            + (1 - p_known) * self.p_guess
        )

        p_incorrect = (
            p_known * self.p_slip
            + (1 - p_known) * (1 - self.p_guess)
        )

        # -----------------------------------------
        # STEP 2: Bayesian update
        # -----------------------------------------

        if correct:

            p_known_given_answer = (
                p_known * (1 - self.p_slip)
            ) / p_correct

        else:

            p_known_given_answer = (
                p_known * self.p_slip
            ) / p_incorrect

        # -----------------------------------------
        # STEP 3: Learning transition
        # -----------------------------------------

        p_known_after_learning = (
            p_known_given_answer
            + (1 - p_known_given_answer) * self.p_learn
        )

        # -----------------------------------------
        # STEP 4: Keep value between 0 and 1
        # -----------------------------------------

        p_known_after_learning = max(
            0.0,
            min(1.0, p_known_after_learning)
        )

        state.p_known = p_known_after_learning

        return round(state.p_known, 2)

    def get_difficulty(self, topic: str) -> str:

        mastery = self.get_mastery(topic)

        if mastery < 0.40:
            return "easy"

        if mastery < 0.70:
            return "medium"

        return "hard"

    def get_weakest_topic(self) -> str | None:

        if not self.topic_states:
            return None

        weakest_topic = min(
            self.topic_states,
            key=lambda topic: self.topic_states[topic].p_known
        )

        return weakest_topic