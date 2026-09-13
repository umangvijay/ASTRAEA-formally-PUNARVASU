"""Registers every model module on SQLAlchemy's Base.metadata — import this, not individual models."""

from app.core import models as core  # noqa: F401
from app.sentinel import models as sentinel  # noqa: F401
from app.loom import models as loom  # noqa: F401
from app.pulse import models as pulse  # noqa: F401
from app.shield import models as shield  # noqa: F401
from app.vaani import models as vaani  # noqa: F401
from app.forge import models as forge  # noqa: F401
from app.shared.benchmarks import Benchmark  # noqa: F401
