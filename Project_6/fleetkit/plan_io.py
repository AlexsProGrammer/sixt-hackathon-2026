"""Write a plan in the submission format."""

from pathlib import Path

import pandera.pandas as pa
import pandera.typing as pat

from fleetkit.schemas import PlanSchema

DATE_FORMAT = "%Y-%m-%d"


@pa.check_types
def write_plan(*, df_plan: pat.DataFrame[PlanSchema], path: Path) -> None:
    """Validate the plan format (not the feasibility) and write it as CSV.

    An empty plan is valid and gives a file with the header only.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df_plan.to_csv(path, index=False, date_format=DATE_FORMAT)
