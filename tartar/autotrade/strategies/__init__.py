"""Strategies the agent can run. Add one by implementing core.Strategy and registering its kind here."""

from .dip import DipStrategy
from .external import ExternalSignals
from .jlp_hedged import JLPHedged
from .pumpflow import PumpFlow
from .xs_momentum import XSMomentum

REGISTRY = {"dip": DipStrategy, "xs_momentum": XSMomentum, "external": ExternalSignals, "pumpflow": PumpFlow,
            "jlp_hedged": JLPHedged}
