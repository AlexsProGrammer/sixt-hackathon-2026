"""Convert a plan for the total fleet into a plan per car category."""

import numpy as np
import pandas as pd
import pandera.typing as pat

from fleetkit.baseline import current_cars
from fleetkit.loader import Instance
from fleetkit.rounding import largest_remainder
from fleetkit.schemas import (
    CATEGORY_ORDER,
    CategoryShareSchema,
    PlanSchema,
    StationFleetSchema,
    StationSchema,
    TotalPlanSchema,
)

sfl = StationFleetSchema
share = CategoryShareSchema
tot = TotalPlanSchema
plan = PlanSchema


def _category_shares(*, instance: Instance) -> pat.DataFrame[CategoryShareSchema]:
    """Share of each category in the day-1 fleet of the station.

    A station without cars gets the shares of the whole network.
    """
    total_col = "_total"
    df_cars = current_cars(instance=instance)
    network = df_cars.groupby(sfl.category)[sfl.cars].sum() / df_cars[sfl.cars].sum()
    return pat.DataFrame[CategoryShareSchema](
        df_cars.assign(
            **{total_col: lambda df_: df_.groupby(sfl.station_id)[sfl.cars].transform("sum")}
        )
        .assign(
            **{
                share.share: lambda df_: np.where(
                    df_[total_col] > 0,
                    df_[sfl.cars] / df_[total_col].where(df_[total_col] > 0, 1),
                    df_[sfl.category].map(network),
                )
            }
        )
        .loc[:, [share.station_id, share.category, share.share]]
    )


def split_total_plan(
    *, df_total_plan: pat.DataFrame[TotalPlanSchema], instance: Instance
) -> pat.DataFrame[PlanSchema]:
    """Split each row of a total-fleet plan over the categories.

    The cars of a row go to the categories in proportion to the category shares of the
    origin station in the day-1 fleet, rounded with the largest remainder rule.
    A category with 0 cars gets no row.
    """
    categories = [c.value for c in CATEGORY_ORDER]
    stations = instance.stations[StationSchema.station_id].tolist()
    shares = (
        _category_shares(instance=instance)
        .pivot(index=share.station_id, columns=share.category, values=share.share)
        .reindex(index=stations, columns=categories)
    )
    pos = pd.Index(shares.index).get_indexer(df_total_plan[tot.station_id])
    if (pos < 0).any():
        unknown = sorted(set(df_total_plan[tot.station_id]) - set(stations))
        raise ValueError(f"Unknown station in total plan: {unknown}")
    cars = largest_remainder(
        weights=shares.to_numpy()[pos], totals=df_total_plan[tot.cars].to_numpy()
    )
    row_idx, cat_idx = np.nonzero(cars)
    return pat.DataFrame[PlanSchema](
        df_total_plan.take(row_idx)
        .reset_index(drop=True)
        .assign(
            **{
                plan.category: np.array(categories)[cat_idx],
                plan.cars: cars[row_idx, cat_idx],
            }
        )
        .loc[
            :,
            [
                plan.action,
                plan.date,
                plan.category,
                plan.station_id,
                plan.to_station_id,
                plan.mode,
                plan.cars,
            ],
        ]
    )
