def decide(history):
    if not history:
        return COOPERATE
    return history[-1].opponent
