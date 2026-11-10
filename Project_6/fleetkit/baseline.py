"""The baseline plan: a simple rule for Level 1, without optimization."""

import numpy as np
import pandas as pd
import pandera.typing as pat
from pandera.pandas import Field

from fleetkit.loader import Instance
from fleetkit.rounding import largest_remainder
from fleetkit.schemas import (
    CATEGORY_ORDER,
    Action,
    BaseSchema,
    Category,
    CategorySchema,
    FleetSnapshotSchema,
    HorizonSchema,
    PlanSchema,
    ReservationSchema,
    ReservationStatus,
    StationFleetSchema,
    StationSchema,
    VehicleStatus,
)

HISTORY_DAYS = 56

sfl = StationFleetSchema
snap = FleetSnapshotSchema
res = ReservationSchema
stn = StationSchema
cat = CategorySchema
plan = PlanSchema


class NeededCarsSchema(BaseSchema):
    """Cars per station and category to carry the average load, as a real number."""

    station_id: str
    category: str = Field(isin=[e.value for e in Category])
    needed_cars: float = Field(ge=0)


class StationCategorySchema(BaseSchema):
    """All combinations of station and car category."""

    station_id: str
    category: str = Field(isin=[e.value for e in Category])


need = NeededCarsSchema
key_cols = [sfl.station_id, sfl.category]


def _grid(*, instance: Instance) -> pat.DataFrame[StationCategorySchema]:
    return pat.DataFrame[StationCategorySchema](
        instance.stations[[stn.station_id]].merge(instance.categories[[cat.category]], how="cross")
    )


def current_cars(*, instance: Instance) -> pat.DataFrame[StationFleetSchema]:
    """Idle cars at the station plus cars on rent that were picked up there, on day 1.

    A combination without cars has 0 cars.
    """
    idle = instance.fleet_snapshot.query(f"{snap.status} == '{VehicleStatus.IDLE}'").loc[
        :, key_cols
    ]
    on_rent = (
        instance.fleet_snapshot.query(f"{snap.status} == '{VehicleStatus.ON_RENT}'")
        .drop(columns=[snap.station_id])
        .merge(
            instance.reservations[[res.reservation_id, res.pickup_station_id]],
            on=snap.reservation_id,
            validate="many_to_one",
        )
        .rename(columns={res.pickup_station_id: sfl.station_id})
        .loc[:, key_cols]
    )
    df_counts = (
        pd.concat([idle, on_rent], ignore_index=True)
        .groupby(key_cols, as_index=False)
        .size()
        .rename(columns={"size": sfl.cars})
    )
    return pat.DataFrame[StationFleetSchema](
        _grid(instance=instance)
        .merge(df_counts, on=key_cols, how="left", validate="one_to_one")
        .fillna({sfl.cars: 0})
    )


def _needed_cars(*, instance: Instance) -> pat.DataFrame[NeededCarsSchema]:
    """Pickups per day times rental length, divided by the maximum utilization.

    Pickups per day: reservations that start before day 1, divided by the 8 history weeks.
    Rental length: average of the completed rentals of the category, in days.
    A combination without history has need 0.
    """
    pickups_col, length_col = "_pickups", "_length"
    df_pickups = (
        instance.reservations.query(f"{res.status} != '{ReservationStatus.BOOKED}'")
        .groupby([res.pickup_station_id, res.category], as_index=False)
        .size()
        .rename(columns={res.pickup_station_id: sfl.station_id, "size": pickups_col})
    )
    df_length = (
        instance.reservations.query(f"{res.status} == '{ReservationStatus.COMPLETED}'")
        .assign(
            **{length_col: lambda df_: (df_[res.return_date] - df_[res.pickup_date]).dt.days + 1}
        )
        .groupby(res.category, as_index=False)[length_col]
        .mean()
    )
    return pat.DataFrame[NeededCarsSchema](
        _grid(instance=instance)
        .merge(df_pickups, on=key_cols, how="left", validate="one_to_one")
        .merge(df_length, on=res.category, how="left", validate="many_to_one")
        .merge(
            instance.stations[[stn.station_id, stn.max_utilization]],
            on=stn.station_id,
            validate="many_to_one",
        )
        .fillna({pickups_col: 0.0, length_col: 0.0})
        .assign(
            **{
                need.needed_cars: lambda df_: (
                    df_[pickups_col] / HISTORY_DAYS * df_[length_col] / df_[stn.max_utilization]
                )
            }
        )
    )


def baseline_plan(*, instance: Instance) -> pat.DataFrame[PlanSchema]:
    """Add cars on day 1 where the need is above the current fleet; no removals, no transfers.

    One row per station and category with at least 1 added car.
    The additions of a category are rounded to whole cars and scaled down to the addition cap.
    """
    gap_col = "_gap"
    df_gap = (
        _needed_cars(instance=instance)
        .merge(current_cars(instance=instance), on=key_cols, validate="one_to_one")
        .assign(**{gap_col: lambda df_: (df_[need.needed_cars] - df_[sfl.cars]).clip(lower=0)})
    )
    stations = instance.stations[stn.station_id].tolist()
    categories = [c.value for c in CATEGORY_ORDER]
    weights = (
        df_gap.pivot(index=sfl.category, columns=sfl.station_id, values=gap_col)
        .reindex(index=categories, columns=stations)
        .to_numpy()
    )
    caps = instance.categories.set_index(cat.category)[cat.addition_cap]
    totals = np.minimum(
        caps.reindex(categories).to_numpy(), np.floor(weights.sum(axis=1) + 0.5)
    ).astype(int)
    cars = largest_remainder(weights=weights, totals=totals)
    cat_idx, station_idx = np.nonzero(cars)
    return pat.DataFrame[PlanSchema](
        pd.DataFrame(
            {
                plan.action: Action.ADD.value,
                plan.date: instance.horizon[HorizonSchema.first_date].iloc[0],
                plan.category: np.array(categories)[cat_idx],
                plan.station_id: np.array(stations)[station_idx],
                plan.to_station_id: None,
                plan.mode: None,
                plan.cars: cars[cat_idx, station_idx],
            }
        )
    )
