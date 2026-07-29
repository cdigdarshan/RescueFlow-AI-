import sys
from types import ModuleType

import numpy as np
from scipy.optimize import linear_sum_assignment


def ensure_lap_compatibility():
    """Provide the small `lap` API ByteTrack needs by using SciPy's solver."""
    try:
        import lap  # noqa: F401

        return
    except ImportError:
        pass

    compatibility_module = ModuleType("lap")
    compatibility_module.__version__ = "scipy-compat-1.0"
    compatibility_module.lapjv = _lapjv
    sys.modules.setdefault("lap", compatibility_module)


def _lapjv(cost_matrix, extend_cost=True, cost_limit=np.inf):
    del extend_cost
    costs = np.asarray(cost_matrix)
    row_assignment = np.full(costs.shape[0], -1, dtype=int)
    column_assignment = np.full(costs.shape[1], -1, dtype=int)

    if costs.size == 0:
        return 0.0, row_assignment, column_assignment

    rows, columns = linear_sum_assignment(costs)
    total_cost = 0.0
    for row, column in zip(rows, columns):
        if costs[row, column] > cost_limit:
            continue
        row_assignment[row] = column
        column_assignment[column] = row
        total_cost += float(costs[row, column])
    return total_cost, row_assignment, column_assignment
