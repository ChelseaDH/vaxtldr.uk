import math
from collections import defaultdict
from datetime import date
from typing import Iterable, DefaultDict

import numpy as np
import pandas as pd

from data.types import Source, Vaccinated, Slice


def parse(source: Source, df: pd.DataFrame) -> Iterable[Vaccinated]:
    # Data overrides. Some data formats are only used once, and not worth writing parsers for.
    if source.data_date == date(2021, 1, 7) and source.period == "weekly":
        return [
            Vaccinated(source, 438075, Slice("1", "<80", "all")),
            Vaccinated(source, 13567, Slice("2", "<80", "all")),
            Vaccinated(source, 654810, Slice("1", ">=80", "all")),
            Vaccinated(source, 6414, Slice("2", ">=80", "all")),
        ]
    elif source.data_date == date(2020, 12, 31) and source.period == "weekly":
        return [
            Vaccinated(source, 261561, Slice("1", "<80", "all")),
            Vaccinated(source, 0, Slice("2", "<80", "all")),
            Vaccinated(source, 524439, Slice("1", ">=80", "all")),
            Vaccinated(source, 0, Slice("2", ">=80", "all")),
        ]

    if source.period == "daily":
        if source.data_date >= date(2021, 1, 18):
            return __parse_df_from_2021_01_18(source, df)
        else:
            return __parse_df_earliest(source, df)
    elif source.period == "weekly":
        return __parse_df_weekly(source, df)
    else:
        raise AssertionError()


def __parse_df_from_2021_01_18(source: Source, df: pd.DataFrame) -> Iterable[Vaccinated]:
    df = df.drop("Unnamed: 0", axis=1)
    df_iterrows = df.iterrows()

    for row in df_iterrows:
        _, (title, *data) = row
        if type(title) == str and title.lower() == "region of residence":
            break

    for row in df_iterrows:
        _, (location, *data) = row
        if type(location) == float and math.isnan(location):
            continue
        if location == "Data quality notes:":
            break
        dose_1, dose_2, cumulative = filter(lambda d: not math.isnan(d), data)
        if location == "Total":
            location = "all"
        yield Vaccinated(source, dose_1, Slice(location=location, dose="1"))
        yield Vaccinated(source, dose_2, Slice(location=location, dose="2"))
        yield Vaccinated(source, cumulative, Slice(location=location, dose="all"))


def __parse_df_earliest(source: Source, df: pd.DataFrame) -> Iterable[Vaccinated]:
    df = df.drop("Unnamed: 0", axis=1)
    for row in df.iterrows():
        _, (title, *data) = row
        if type(title) == str and " to " in title and len(title.split()) == 7:
            dose = "all"
        elif type(title) == str and title.strip().lower() == "of which, 1st dose":
            dose = "1"
        elif type(title) == str and title.strip().lower() == "of which, 2nd dose":
            dose = "2"
        else:
            continue
        vaccinated = data[1]
        yield Vaccinated(source, vaccinated, Slice(dose=dose))


def __parse_df_weekly(source: Source, df: pd.DataFrame) -> Iterable[Vaccinated]:
    def is_start(cell) -> bool:
        return type(cell) == str and (
            cell.lower() == "region of residence" or cell.lower() == "nhs region of residence"
        )

    def is_end(cell) -> bool:
        return type(cell) == str and cell.lower() == "data quality notes:"

    def is_nan(cell) -> bool:
        return type(cell) == float and math.isnan(cell)

    a = df.to_numpy()

    # Trim.
    (start_y,), (start_x,) = np.where(np.vectorize(is_start)(a))
    (end_y,), (_,) = np.where(np.vectorize(is_end)(a))
    a = a[start_y:end_y, start_x:]

    # Remove NaNs.
    is_nans = np.vectorize(is_nan)(a)
    a = a[:, ~np.all(is_nans, axis=0)]
    a = a[~np.all(is_nans, axis=1), :]

    # Fill in dose row.
    filled_in_doses = []
    current_dose = None
    for population in a[0, 1:]:
        if not is_nan(population):
            current_dose = population
        filled_in_doses.append(current_dose)
    a[0, 1:] = filled_in_doses

    vaccinated_by_slice: DefaultDict[Slice, int] = defaultdict(int)

    for y in range(2, a.shape[0]):
        for x in range(1, a.shape[1]):
            dose = a[0, x]
            group = a[1, x]
            location = a[y, 0]
            vaccinated = a[y, x]

            if dose == "1st dose":
                dose = "1"
            if dose == "2nd dose":
                dose = "2"
            if group == "80+":
                group = ">=80"
            else:
                group = "<80"
            if location == "Total":
                location = "all"

            vaccinated_by_slice[Slice(dose, group, location)] += vaccinated

    for slice_, vaccinated in vaccinated_by_slice.items():
        yield Vaccinated(source, vaccinated, slice_)
