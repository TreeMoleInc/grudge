_betrayed = False


def decide(history):
    global _betrayed
    if history and history[-1].opponent == DEFECT:
        _betrayed = True
    return DEFECT if _betrayed else COOPERATE
