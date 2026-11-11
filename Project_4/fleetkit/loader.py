"""Read and validate the team data files."""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pandera.typing as pat

from fleetkit.schemas import (
    CategorySchema,
    CheckValueSchema,
    DistanceSchema,
    FleetSnapshotSchema,
    HorizonSchema,
    PriceFactorSchema,
    ReservationSchema,
    StationSchema,
    TransferCostSchema,
)


@dataclass(frozen=True)
class Instance:
    """All team data tables, validated."""

    horizon: pat.DataFrame[HorizonSchema]
    stations: pat.DataFrame[StationSchema]
    distances: pat.DataFrame[DistanceSchema]
    categories: pat.DataFrame[CategorySchema]
    transfer_costs: pat.DataFrame[TransferCostSchema]
    price_factors: pat.DataFrame[PriceFactorSchema]
    fleet_snapshot: pat.DataFrame[FleetSnapshotSchema]
    reservations: pat.DataFrame[ReservationSchema]
    check_values: pat.DataFrame[CheckValueSchema]


def load_instance(*, data_dir: Path) -> Instance:
    """Read all team data files from `data_dir` and validate them."""
    data_dir = Path(data_dir)

    def read(name: str) -> pd.DataFrame:
        return pd.read_csv(data_dir / name)

    return Instance(
        horizon=pat.DataFrame[HorizonSchema](HorizonSchema.validate(read("horizon.csv"))),
        stations=pat.DataFrame[StationSchema](StationSchema.validate(read("stations.csv"))),
        distances=pat.DataFrame[DistanceSchema](DistanceSchema.validate(read("distances.csv"))),
        categories=pat.DataFrame[CategorySchema](CategorySchema.validate(read("categories.csv"))),
        transfer_costs=pat.DataFrame[TransferCostSchema](
            TransferCostSchema.validate(read("transfer_costs.csv"))
        ),
        price_factors=pat.DataFrame[PriceFactorSchema](
            PriceFactorSchema.validate(read("price_factors.csv"))
        ),
        fleet_snapshot=pat.DataFrame[FleetSnapshotSchema](
            FleetSnapshotSchema.validate(read("fleet_snapshot.csv"))
        ),
        reservations=pat.DataFrame[ReservationSchema](
            ReservationSchema.validate(read("reservations.csv"))
        ),
        check_values=pat.DataFrame[CheckValueSchema](
            CheckValueSchema.validate(read("check_values.csv"))
        ),
    )
