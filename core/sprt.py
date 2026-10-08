"""
Clarion Sequential Causal Verification Engine
Combines Behavioral Markov Modeling (State Transitions) with Wald's SPRT.
Formulation adapted from Runtime-Verify architecture.
"""
import math
from typing import List, Dict, Any, Tuple


class MarkovCausalModel:
    def __init__(self):
        # Baseline normal transition probabilities P(S_t | S_{t-1}, H0)
        self.p_h0 = {
            ("BASELINE", "CONFIG_MUTATION"): 0.05,
            ("CONFIG_MUTATION", "DB_LOCK_SURGE"): 0.01,
            ("DB_LOCK_SURGE", "COMPLETION_DROP"): 0.02,
            ("COMPLETION_DROP", "GATEWAY_502_ALARM"): 0.01,
            ("BASELINE", "GATEWAY_502_ALARM"): 0.03,
            ("GATEWAY_502_ALARM", "COMPLETION_DROP"): 0.20,
            ("COMPLETION_DROP", "UPI_CAPTURE_NORMAL"): 0.85,
        }
        # Incident anomaly transition probabilities P(S_t | S_{t-1}, H1)
        self.p_h1 = {
            ("BASELINE", "CONFIG_MUTATION"): 0.85,
            ("CONFIG_MUTATION", "DB_LOCK_SURGE"): 0.94,
            ("DB_LOCK_SURGE", "COMPLETION_DROP"): 0.96,
            ("COMPLETION_DROP", "GATEWAY_502_ALARM"): 0.91,
            ("BASELINE", "GATEWAY_502_ALARM"): 0.04,
            ("GATEWAY_502_ALARM", "COMPLETION_DROP"): 0.05,
            ("COMPLETION_DROP", "UPI_CAPTURE_NORMAL"): 0.15,  # If gateway crashed, UPI shouldn't be 98.6%
        }
        self.epsilon = 1e-4

    def transition_likelihood_ratio(self, prev_state: str, curr_state: str) -> Tuple[float, float, float]:
        key = (prev_state, curr_state)
        prob_h1 = self.p_h1.get(key, self.epsilon)
        prob_h0 = self.p_h0.get(key, self.epsilon)
        lr = prob_h1 / prob_h0
        return lr, prob_h1, prob_h0


class WaldSPRT:
    def __init__(self, alpha: float = 0.01, beta: float = 0.05):
        self.alpha = alpha
        self.beta = beta
        self.upper_bound_A = math.log((1.0 - beta) / alpha)       # ~ +4.554
        self.lower_bound_B = math.log(beta / (1.0 - alpha))       # ~ -2.986

    def evaluate_chain(
        self, 
        hypothesis_id: str, 
        prior_probability: float, 
        transitions: List[Tuple[str, str]]
    ) -> Dict[str, Any]:
        markov = MarkovCausalModel()
        p_clamped = max(0.001, min(0.999, prior_probability))
        z_cumulative = math.log(p_clamped / (1.0 - p_clamped))
        
        trajectory = []
        verdict = "INCONCLUSIVE"
        stopping_step = None

        for idx, (s_prev, s_curr) in enumerate(transitions):
            lr, p_h1, p_h0 = markov.transition_likelihood_ratio(s_prev, s_curr)
            log_lr = math.log(lr)
            z_cumulative += log_lr

            step_entry = {
                "step": idx + 1,
                "transition": f"{s_prev} -> {s_curr}",
                "lr": round(lr, 3),
                "log_lr": round(log_lr, 4),
                "z_score": round(z_cumulative, 4),
            }
            trajectory.append(step_entry)

            if stopping_step is None:
                if z_cumulative >= self.upper_bound_A:
                    verdict = "ROOT_CAUSE"
                    stopping_step = idx + 1
                elif z_cumulative <= self.lower_bound_B:
                    verdict = "SUPPRESSED_NOISE"
                    stopping_step = idx + 1

        if stopping_step is None:
            if z_cumulative <= self.lower_bound_B:
                verdict = "SUPPRESSED_NOISE"
            elif z_cumulative >= self.upper_bound_A:
                verdict = "ROOT_CAUSE"
            elif z_cumulative > 0:
                verdict = "CONTRIBUTING"
            else:
                verdict = "INCONCLUSIVE"

        posterior = 1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, z_cumulative))))

        return {
            "hypothesis_id": hypothesis_id,
            "verdict": verdict,
            "stopping_step": stopping_step or len(transitions),
            "final_z_score": round(z_cumulative, 4),
            "posterior_probability": round(posterior, 4),
            "upper_bound_A": round(self.upper_bound_A, 4),
            "lower_bound_B": round(self.lower_bound_B, 4),
            "trajectory": trajectory
        }
