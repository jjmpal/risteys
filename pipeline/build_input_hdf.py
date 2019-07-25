"""
Takes the input CSV files and merge them into one HDF5 file.

Steps:
- filter out endpoints that are too broad
- filter out endpoints that are comorbidities
- for each individual, sort their events by date
- merge events that are within a 30-day time window

Usage:
    python build_input_hdf.py <path-to-data-dir>

Input files:
- FINNGEN_ENDPOINTS_longitudinal.txt
  Each row is an event with FinnGen ID, Endpoint and time information.
  Source: FinnGen data
- FINNGEN_MINIMUM_DATA.txt
  Each row is an individual in FinnGen with some information.
  Source: FinnGen data
- Endpoint_definitions_FINNGEN_ENDPOINTS.tsv
  Each row is an endpoint definition.
  Source: PheWeb
- COV_PHENO.txt
  Each row is an individual in FinnGen, with FinnGen ID. Only these
  individuals will be used for data processing in PheWeb.
  Source: FinnGen data
"""
from csv import excel_tab
from pathlib import Path
from sys import argv

import numpy as np
import pandas as pd

from log import logger


INPUT_ENDPOINTS = "Endpoint_definitions_FINNGEN_ENDPOINTS.tsv"
INPUT_LONGIT = "FINNGEN_ENDPOINTS_longitudinal.txt"
INPUT_INFO = "FINNGEN_MINIMUM_DATA.txt"
INPUT_SAMPLES = "COV_PHENO.txt"
OUTPUT_NAME = "input.hdf5"


def prechecks(endpoints_path, longit_path, info_path, samples_path, output_path):
    """Perform checks before running to fail earlier rather than later"""
    logger.info("Performing pre-checks")
    assert endpoints_path.exists()
    assert longit_path.exists()
    assert info_path.exists()
    assert not output_path.exists()

    # Check endpoint file headers
    df = pd.read_csv(endpoints_path, dialect=excel_tab, nrows=0)
    assert "NAME" in df.columns
    assert "OMIT" in df.columns
    assert "LEVEL" in df.columns
    assert "TAGS" in df.columns

    # Check event file headers
    df = pd.read_csv(longit_path, dialect=excel_tab, nrows=0)
    cols = list(df.columns)
    expected_cols = ["FINNGENID", "EVENT_AGE", "EVENT_YEAR", "ENDPOINT"]
    assert cols == expected_cols

    # Check sex for all individuals
    df = pd.read_csv(info_path, dialect=excel_tab, usecols=["FINNGENID", "SEX"])
    sexs = df["SEX"].unique()
    sexs = set(sexs)
    expected_sexs = set(["female", "male"])
    assert sexs == expected_sexs

    # Check samples file headers
    df = pd.read_csv(samples_path, dialect=excel_tab, nrows=0)
    assert "FINNGENID" in df.columns


def main(endpoints_path, longit_path, info_path, samples_path, output_path):
    """Clean up and merge all the input files into one HDF5 file"""
    prechecks(endpoints_path, longit_path, info_path, samples_path, output_path)

    data = parse_data(longit_path, info_path)

    data = filter_out_samples(data, samples_path)

    logger.info("Filtering out the endpoints.")
    endpoints = filter_out_endpoints(endpoints_path)
    (nbefore, _) = data.shape
    data = data.merge(endpoints, on="ENDPOINT")
    (nafter, _) = data.shape
    log_event_reduction(nbefore, nafter)

    data = sort_events(data)

    data = merge_events(data)

    logger.info(f"Writing merged and filtered input data to HDF5 file {output_path}")
    data.to_hdf(output_path, "/data")


def parse_data(longit_file, mindata_file):
    """Parse the events file and mindata file to build a coherent DataFrame.

    NOTE:
    At this point we might want to write out the loaded data as a
    DataFrame so it can be re-loaded later on. However doing this adds
    the cost for: writing out the DataFrame the first time + loading
    the DataFrame each time. After few measurements it turns out this
    doesn't save that much time.
    """
    logger.info("Parsing 'longitudinal file' and 'mininimum data file' into DataFrames")
    df = pd.read_csv(
        longit_file,
        dialect=excel_tab,
        dtype={
            "FINNGENID": np.object,
            "EVENT_AGE": np.float64,
            "EVENT_YEAR": np.int64,
            "ENDPOINT": np.object,
    })

    # Loading data file with ID -> SEX info
    dfsex = pd.read_csv(
        mindata_file,
        dialect=excel_tab,
        usecols=["FINNGENID", "SEX"],
        dtype={
            "FINNGENID": np.object,
            "SEX": "category",
    })

    # Perform one-hot encoding for SEX so it can be written to HDF
    # without the slow format="table".
    onehot = pd.get_dummies(dfsex["SEX"])
    dfsex = pd.concat([dfsex, onehot], axis=1)
    dfsex = dfsex.drop("SEX", axis=1)

    logger.debug("Merging longitudinal and sex DataFrames")
    df = df.merge(dfsex, on="FINNGENID")

    return df


def filter_out_samples(data, samples_path):
    """Filter out samples, select only the one included in PheWeb."""
    logger.info("Filtering out the samples.")
    (nbefore, _) = data.shape
    samples = pd.read_csv(samples_path, dialect=excel_tab, usecols=["FINNGENID"])
    data = data.merge(samples, on="FINNGENID")
    (nafter, _) = data.shape

    log_event_reduction(nbefore, nafter)
    return data


def filter_out_endpoints(filepath):
    """Get endpoints that are not too broad"""
    df = pd.read_csv(
        filepath,
        dialect=excel_tab,
        usecols=["NAME", "OMIT", "LEVEL", "TAGS"],
        skiprows=[1]  # this row contains the comment info on the file version
    )
    mask_level = df["LEVEL"] != '1'
    mask_omit = df["OMIT"].isna()

    comorb = df["TAGS"].apply(is_comorb)
    mask_comorb = ~comorb

    df = df[mask_level & mask_omit & mask_comorb]
    df = df.drop(["OMIT", "LEVEL", "TAGS"], axis="columns").rename({"NAME": "ENDPOINT"}, axis="columns")

    return df


def log_event_reduction(nbefore, nafter):
    logger.debug(f"Events reduced from {nbefore} to {nafter} (𝚫 = {nbefore - nafter}, {(nbefore - nafter) / nbefore * 100:.1f} %)")


def is_comorb(tags):
    """Return True if the endpoint is a comorbidity, False otherwise."""
    comorb_suffix = "_CM"
    tags = tags.split(",")
    tags = map(lambda tag: tag.endswith(comorb_suffix), tags)
    return all(tags)


def sort_events(data):
    """Sort data by event date, grouping them by FinnGen ID"""
    logger.info("Sorting the events by FinnGenID > Endpoint > Event age")
    return data.sort_values(by=["FINNGENID", "ENDPOINT", "EVENT_AGE"])


def merge_events(df):
    """Merge events of same individual and endpoint if less than 30 days apart.

    NOTE: assumes rows are sorted by FINNGENID, ENDPOINT, EVENT_AGE
    will lead to wrong result otherwise.
    """
    logger.info("Merging events with 30-day time window")
    window = 30/365.25

    shifted = df.shift()
    shifted["end"] = shifted.EVENT_AGE + window

    # Compare only same individual & same endpoint, then check if time
    # difference between 2 successive events is less than the time
    # window.
    skip = (
        (df.FINNGENID == shifted.FINNGENID)
        & (df.ENDPOINT == shifted.ENDPOINT)
        & (df.EVENT_AGE <= shifted.end)
    )
    df_merged = df[~ skip]
    return df_merged


if __name__ == '__main__':
    DATA_DIR = Path(argv[1])

    main(
        DATA_DIR / INPUT_ENDPOINTS,
        DATA_DIR / INPUT_LONGIT,
        DATA_DIR / INPUT_INFO,
        DATA_DIR / INPUT_SAMPLES,
        DATA_DIR / OUTPUT_NAME,
    )
