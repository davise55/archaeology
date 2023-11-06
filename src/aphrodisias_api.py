import requests
import bs4 as BeautifulSoup
import pandas as pd
import geopandas as gpd
import numpy as np
import io
import re

handle_prefix = "2027.42"
mich_url = "https://deepblue.lib.umich.edu/"
handle_url = "http://hdl.handle.net/"


"https://deepblue.lib.umich.edu/handle/2027.42/89592/browse?type=title"
"https://deepblue.lib.umich.edu/handle/2027.42/89592/browse?rpp=25&sort_by=1&type=title&offset=25&etal=-1&order=ASC"
"https://deepblue.lib.umich.edu/handle/2027.42/89592/browse?rpp=25&sort_by=1&type=title&offset=50&etal=-1&order=ASC"

num_entries = 738
entries_per_page = 25
url_list = ["https://deepblue.lib.umich.edu/handle/2027.42/89592/browse?type=title"] + [
    f"https://deepblue.lib.umich.edu/handle/2027.42/89592/browse?rpp=25&sort_by=1&type=title&offset={i}&etal=-1&order=ASC"
    for i in range(25, num_entries, 25)
]

handles = []
for i, url in enumerate(url_list):
    print(f"{i+1} of {len(url_list)}")
    r = requests.get(url)
    soup = BeautifulSoup.BeautifulSoup(r.content, "html.parser")
    handle_entry_list = soup.find_all("div", class_="artifact-title")
    for handle in handle_entry_list:
        print(handle.find("a"))
        handles.append(handle.find("a").get("href"))

df_list = []
for i, handle in enumerate(handles):
    print(f"{i+1} of {len(handles)}")
    r = requests.get(f"https://deepblue.lib.umich.edu/{handle}?show=full")

    soup = BeautifulSoup.BeautifulSoup(r.content, "html.parser")
    table = soup.find_all("table")
    df = pd.read_html(io.StringIO(str(table)))[0]
    df[0] = df[0].str.replace("dc.", "")
    # df.set_index(0, inplace=True)
    df_list.append(df)


def rename_duplicates(names):
    seen = dict()

    for i, name in enumerate(names):
        if name not in seen:
            seen[name] = 0
        else:
            seen[name] += 1
            names[i] += f"_{seen[name]}"

    return names


processed_df_list = []
for i, df in enumerate(df_list):
    print(f"{i+1} of {len(df_list)}")
    description_bool = df[0] == "description"
    df_copy = df.copy()
    df_copy[0].mask(
        description_bool,
        df_copy[1].apply(lambda x: x.split(": ")[0].lower()),
        inplace=True,
    )
    df_copy[1].mask(
        description_bool,
        df_copy[1].apply(lambda x: ": ".join(x.split(": ")[1:])),
        inplace=True,
    )
    df_copy[0] = rename_duplicates(df_copy[0])
    df_copy = df_copy.set_index(0).T[:1]
    processed_df_list.append(df_copy)

result_df = pd.concat(processed_df_list, ignore_index=True)
result_df.rename(
    {
        "latitude": "latitude_dms",
        "longitude": "longitude_dms",
    },
    axis=1,
    inplace=True,
)

# Duplicate rows if multiple lat/lon values
non_latlon = result_df.columns[~result_df.columns.str.contains("dms")].tolist()
result_df = (
    result_df.set_index(non_latlon)
    .apply(lambda x: x.str.split(",").explode())
    .reset_index()
)


def dms_and_ddm_to_dec(input_val):
    input_val = str(input_val)
    if len(input_val.split(".")) == 3:
        deg, minutes, minutes_decimal = input_val.split(".")
        val = float(deg) + (float(".".join([minutes, minutes_decimal]))) / 60
    elif len(input_val.split(".")) == 4:
        deg, minutes, seconds, seconds_decimal = input_val.split(".")
        val = (
            float(deg)
            + float(minutes) / 60
            + (float(".".join([seconds, seconds_decimal]))) / (60 * 60)
        )
    else:
        val = input_val
    return val


result_df["latitude"] = result_df["latitude_dms"].apply(dms_and_ddm_to_dec)
result_df["longitude"] = result_df["longitude_dms"].apply(dms_and_ddm_to_dec)


column_filter = [
    "contributor.author",
    "date.accessioned",
    "date.available",
    "date.issued",
    "identifier.citation",
    "identifier.other",
    "identifier.uri",
    "local name",
    "local information",
    "local informant",
    "latitude_dms",
    "longitude_dms",
    "latitude",
    "longitude",
    "elevation",
    "axis",
    "dimensions",
    "description",
    "finds",
    "relation",
    "title",
    "type",
    "subject.hlbsecondlevel",
    "subject.hlbtoplevel",
    "subject",
    "subject_1",
    "subject_2",
    "subject_3",
    "subject_4",
    "subject_5",
]
result_df = result_df[column_filter]
result_df.to_excel("aphrodisias.xlsx", index=False)

result_gdf = result_df[(result_df.latitude != "nan") | (result_df.longitude != "nan")]
result_gdf = gpd.GeoDataFrame(
    result_gdf,
    geometry=gpd.points_from_xy(result_gdf.longitude, result_gdf.latitude),
    crs="EPSG:4326",
)
result_gdf.to_file("aphrodisias.gpkg", driver="GPKG")
