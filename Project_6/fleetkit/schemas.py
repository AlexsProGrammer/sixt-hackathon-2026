"""Public tables of the fleet allocation challenge: enums and pandera schemas."""

from datetime import datetime
from enum import StrEnum

import pandas as pd
from pandera.pandas import DataFrameModel, Field, dataframe_check


class StationType(StrEnum):
    """Type of a station."""

    AIRPORT = "airport"
    DOWNTOWN = "downtown"


class Category(StrEnum):
    """Car category, in order from lowest to highest."""

    ECONOMY = "economy"
    COMPACT = "compact"
    MIDSIZE = "midsize"
    PREMIUM = "premium"


class VehicleStatus(StrEnum):
    """Status of a vehicle at the start of day 1."""

    IDLE = "idle"
    ON_RENT = "on_rent"


class ReservationStatus(StrEnum):
    """Group of a reservation relative to day 1."""

    COMPLETED = "completed"
    OPEN = "open"
    BOOKED = "booked"


class Action(StrEnum):
    """Type of a plan row."""

    ADD = "add"
    REMOVE = "remove"
    TRANSFER = "transfer"


class TransferMode(StrEnum):
    """How a car moves between two stations."""

    DRIVER = "driver"
    TRUCK = "truck"


CATEGORY_ORDER: tuple[Category, ...] = tuple(Category)
PRICE_SHARES: tuple[float, ...] = (0.6, 0.7, 0.8, 0.9, 1.0)
TRUCK_CAPACITY = 8


class BaseSchema(DataFrameModel):
    class Config:
        strict = "filter"
        coerce = True


class HorizonSchema(BaseSchema):
    """The planning horizon: one row."""

    first_date: datetime
    last_date: datetime


class StationSchema(BaseSchema):
    """One row per station."""

    station_id: str
    station_name: str
    station_type: str = Field(isin=[e.value for e in StationType])
    x_km: float
    y_km: float
    max_utilization: float = Field(gt=0, le=1)

    @dataframe_check
    @classmethod
    def check_unique_key(cls, df: pd.DataFrame) -> bool:
        return not bool(df.duplicated(subset=[cls.station_id], keep=False).any())


class DistanceSchema(BaseSchema):
    """One row per ordered station pair with from not equal to to."""

    from_station_id: str
    to_station_id: str
    distance_km: float = Field(gt=0)
    lead_time_days: int = Field(ge=1)

    @dataframe_check
    @classmethod
    def check_unique_key(cls, df: pd.DataFrame) -> bool:
        return not bool(
            df.duplicated(subset=[cls.from_station_id, cls.to_station_id], keep=False).any()
        )


class CategorySchema(BaseSchema):
    """One row per car category."""

    category: str = Field(isin=[e.value for e in Category])
    rank: int = Field(ge=1, description="1 is the lowest category")
    holding_cost_per_day: float = Field(ge=0)
    addition_cost_per_car: float = Field(ge=0)
    addition_cap: int = Field(ge=0, description="Cap on fleet additions for the whole horizon")
    removal_cap: int = Field(ge=0, description="Cap on fleet removals for the whole horizon")

    @dataframe_check
    @classmethod
    def check_unique_key(cls, df: pd.DataFrame) -> bool:
        return not bool(df.duplicated(subset=[cls.category], keep=False).any())


class TransferCostSchema(BaseSchema):
    """One row per transfer mode."""

    mode: str = Field(isin=[e.value for e in TransferMode])
    fixed_cost: float = Field(ge=0, description="Per car for driver, per truck for truck")
    cost_per_km: float = Field(ge=0, description="Per car for driver, per truck for truck")
    capacity: int = Field(ge=1, description="Cars per vehicle: 1 for driver")

    @dataframe_check
    @classmethod
    def check_unique_key(cls, df: pd.DataFrame) -> bool:
        return not bool(df.duplicated(subset=[cls.mode], keep=False).any())


class PriceFactorSchema(BaseSchema):
    """One row per station type, car category and served share."""

    station_type: str = Field(isin=[e.value for e in StationType])
    category: str = Field(isin=[e.value for e in Category])
    served_share: float = Field(isin=list(PRICE_SHARES))
    price_factor: float = Field(gt=0, description="Average price relative to the base revenue")

    @dataframe_check
    @classmethod
    def check_unique_key(cls, df: pd.DataFrame) -> bool:
        key = [cls.station_type, cls.category, cls.served_share]
        return not bool(df.duplicated(subset=key, keep=False).any())


class FleetSnapshotSchema(BaseSchema):
    """One row per vehicle at the start of day 1."""

    vehicle_id: str
    category: str = Field(isin=[e.value for e in Category])
    status: str = Field(isin=[e.value for e in VehicleStatus])
    station_id: str = Field(nullable=True, description="Set for idle vehicles only")
    reservation_id: str = Field(nullable=True, description="Set for vehicles on rent only")

    @dataframe_check
    @classmethod
    def check_unique_key(cls, df: pd.DataFrame) -> bool:
        return not bool(df.duplicated(subset=[cls.vehicle_id], keep=False).any())

    @dataframe_check
    @classmethod
    def check_location_matches_status(cls, df: pd.DataFrame) -> bool:
        idle = df[cls.status] == VehicleStatus.IDLE
        ok_idle = df.loc[idle, cls.station_id].notna() & df.loc[idle, cls.reservation_id].isna()
        ok_rent = df.loc[~idle, cls.reservation_id].notna() & df.loc[~idle, cls.station_id].isna()
        return bool(ok_idle.all() and ok_rent.all())


class ReservationSchema(BaseSchema):
    """One row per reservation."""

    reservation_id: str
    category: str = Field(isin=[e.value for e in Category])
    pickup_station_id: str
    pickup_date: datetime
    return_station_id: str
    return_date: datetime
    booking_date: datetime
    revenue: float = Field(ge=0, description="Revenue of the whole rental")
    status: str = Field(isin=[e.value for e in ReservationStatus])

    @dataframe_check
    @classmethod
    def check_unique_key(cls, df: pd.DataFrame) -> bool:
        return not bool(df.duplicated(subset=[cls.reservation_id], keep=False).any())


class CheckValueSchema(BaseSchema):
    """Level 0 check values: one row per station, category and date cell."""

    station_id: str
    category: str = Field(isin=[e.value for e in Category])
    date: datetime
    committed_car_days: int = Field(ge=0)
    oneway_arrivals: int = Field(ge=0)
    oneway_departures: int = Field(ge=0)
    station_fleet: int = Field(ge=0, description="Fleet of the cell under the do-nothing plan")


class PlanSchema(BaseSchema):
    """One row per plan decision: add, remove or transfer."""

    action: str = Field(isin=[e.value for e in Action])
    date: datetime
    category: str = Field(isin=[e.value for e in Category])
    station_id: str
    to_station_id: str = Field(nullable=True, description="Transfers only")
    mode: str = Field(nullable=True, description="Transfers only")
    cars: int = Field(ge=1)

    @dataframe_check
    @classmethod
    def check_transfer_columns(cls, df: pd.DataFrame) -> bool:
        transfer = df[cls.action] == Action.TRANSFER
        ok_transfer = df.loc[transfer, cls.to_station_id].notna() & (
            df.loc[transfer, cls.mode].isin([e.value for e in TransferMode])
        )
        ok_other = df.loc[~transfer, cls.to_station_id].isna() & df.loc[~transfer, cls.mode].isna()
        return bool(ok_transfer.all() and ok_other.all())


class TotalPlanSchema(BaseSchema):
    """A plan for the total fleet: like the plan, without a category."""

    action: str = Field(isin=[e.value for e in Action])
    date: datetime
    station_id: str
    to_station_id: str = Field(nullable=True, description="Transfers only")
    mode: str = Field(nullable=True, description="Transfers only")
    cars: int = Field(ge=1)


class StationFleetSchema(BaseSchema):
    """Cars per station and car category at the start of day 1."""

    station_id: str
    category: str = Field(isin=[e.value for e in Category])
    cars: int = Field(ge=0)

    @dataframe_check
    @classmethod
    def check_unique_key(cls, df: pd.DataFrame) -> bool:
        return not bool(df.duplicated(subset=[cls.station_id, cls.category], keep=False).any())


class CategoryShareSchema(BaseSchema):
    """Share of each car category in the fleet of a station."""

    station_id: str
    category: str = Field(isin=[e.value for e in Category])
    share: float = Field(ge=0, le=1)
