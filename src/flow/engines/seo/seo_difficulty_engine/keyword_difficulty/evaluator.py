class CompetitorEvaluator:
    def __init__(self, components, weights):
        self.components = components
        self.weights = weights

    def evaluate(self, ctx) -> float:
        score = 0.0
        for component in self.components:
            weight = self.weights.get(component.name, 0)
            score += component.score(ctx) * weight
        return score
