"""Smoke tests verifying the project scaffold imports cleanly and the
BaseMeasurementSystem interface boundary holds."""

import pytest

from src.diagnostics.metrics import GamingDelta
from src.diagnostics.taxonomy import classify
from src.evaluators.base import BaseMeasurementSystem
from src.evaluators.gold_evaluator import GoldEvaluator
from src.evaluators.s1_observation import S1WeakObservation
from src.evaluators.s2_model import S2WeakModel
from src.evaluators.s3_process import S3WeakProcess
from src.evaluators.s4_robust import S4Robust
from src.optimizers.base_optimizer import BaseOptimizer
from src.optimizers.best_of_n import BestOfNOptimizer


def test_base_measurement_system_cannot_be_instantiated() -> None:
    """BaseMeasurementSystem is abstract and must not be directly instantiable."""
    with pytest.raises(TypeError):
        BaseMeasurementSystem()  # type: ignore[abstract] # pylint: disable=abstract-class-instantiated


def test_base_optimizer_cannot_be_instantiated() -> None:
    """BaseOptimizer is abstract and must not be directly instantiable."""
    with pytest.raises(TypeError):
        BaseOptimizer()  # type: ignore[abstract] # pylint: disable=abstract-class-instantiated


@pytest.mark.parametrize(
    "system_cls,expected_id",
    [
        (GoldEvaluator, "S_star_Gold"),
        (S1WeakObservation, "S1_WeakObservation"),
        (S2WeakModel, "S2_WeakModel"),
        (S3WeakProcess, "S3_WeakProcess"),
        (S4Robust, "S4_Robust"),
    ],
)
def test_measurement_systems_expose_stable_system_id(
    system_cls: type[BaseMeasurementSystem], expected_id: str
) -> None:
    """Each concrete measurement system reports the system_id used in diagnostic records."""
    assert system_cls().system_id == expected_id


def test_measurement_systems_raise_not_implemented_for_now() -> None:
    """Concrete evaluators are stubs until their tickets land."""
    systems = (GoldEvaluator(), S1WeakObservation(), S2WeakModel(), S3WeakProcess(), S4Robust())
    for system in systems:
        with pytest.raises(NotImplementedError):
            system.evaluate("HumanEval/0", "def f(): pass")


def test_best_of_n_raises_not_implemented_for_now() -> None:
    """Best-of-N search is a stub until the generation loop ticket lands."""
    with pytest.raises(NotImplementedError):
        BestOfNOptimizer().search(
            task_id="HumanEval/0",
            prompt="def f():",
            measurement_system=S1WeakObservation(),
            budget_n=1,
            seed=42,
        )


def test_taxonomy_classify_raises_not_implemented_for_now() -> None:
    """AST-based gaming classification is a stub until its ticket lands."""
    with pytest.raises(NotImplementedError):
        classify("def f(): pass")


def test_gaming_delta_computes_difference() -> None:
    """gaming_delta reports Q_meas - Q_true, the primary comparison metric."""
    delta = GamingDelta(
        task_id="HumanEval/0", system_id="S1_WeakObservation", q_meas=1.0, q_true=0.0
    )
    assert delta.gaming_delta == 1.0
