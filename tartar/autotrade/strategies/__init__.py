"""Strategies the agent can run. Add one by implementing core.Strategy and registering its kind here."""

from .dip import DipStrategy
from .external import ExternalSignals
from .jlp_hedged import JLPHedged
from .pumpflow import PumpFlow
from .vault_hold import VaultHold
from .wick_bounce import WickBounce
from .xs_momentum import XSMomentum

REGISTRY = {"dip": DipStrategy, "xs_momentum": XSMomentum, "external": ExternalSignals, "pumpflow": PumpFlow,
            "jlp_hedged": JLPHedged, "vault_hold": VaultHold, "wick_bounce": WickBounce}
