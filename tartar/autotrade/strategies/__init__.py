"""Strategies the agent can run. Add one by implementing core.Strategy and registering its kind here."""

from .dip import DipStrategy
from .external import ExternalSignals
from .xs_momentum import XSMomentum

REGISTRY = {"dip": DipStrategy, "xs_momentum": XSMomentum, "external": ExternalSignals}
