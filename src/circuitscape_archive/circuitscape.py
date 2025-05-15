# Standard Library
import configparser
import itertools
import logging
import math
import os
import shutil
from pathlib import Path

# Third-Party Libraries
import numpy as np
import pygeoprocessing
import rasterio
import rasterio.merge
from osgeo import gdal
from tqdm.auto import tqdm

pathlike = str | Path

# Set up logging
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(threadName)s | %(name)s | %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

TARGET_NODATA = -9999


def _process_circuitscape_inputs(
    cost_surface_raster: pathlike,
    seed_ini: pathlike,
    workspace_path: pathlike,
    tile_size_x=500,
    tile_size_y=500,
):

    # Ensure path compliance
    cost_surface_raster = Path(cost_surface_raster)
    seed_ini = Path(seed_ini)
    workspace_path = Path(workspace_path)

    # Get full cost surface raster information
    ds = gdal.Open(cost_surface_raster)
    band = ds.GetRasterBand(1)
    xsize = band.XSize
    ysize = band.YSize

    # Organize various input variables
    westline_name = "westline_{}_{}.tif"
    eastline_name = "eastline_{}_{}.tif"
    northline_name = "northline_{}_{}.tif"
    southline_name = "southline_{}_{}.tif"

    directions = [
        "we",
        "ew",
        "ns",
        "sn",
    ]

    current_value = 1
    current_dtype = rasterio.int16
    current_nodata = TARGET_NODATA

    # Iterate through each tile in the cost surface raster
    for i, j in tqdm(
        itertools.product(range(0, xsize, tile_size_x), range(0, ysize, tile_size_y)),
        desc="Processing tiles",
        unit="tile",
        total=math.ceil(xsize / tile_size_x) * math.ceil(ysize / tile_size_y),
    ):

        # Create tile folder
        tile_folder = workspace_path / f"{i}_{j}"
        tile_folder.mkdir(exist_ok=True)

        # Clip cost surface into tiles
        tile_raster_path = tile_folder / f"{cost_surface_raster.stem}_tile_{i}_{j}.tif"

        com_string = f"gdal_translate -of GTIFF -srcwin {i}, {j}, {tile_size_x}, {tile_size_y} {cost_surface_raster} {tile_raster_path}"
        os.system(com_string)

        # Clip cost surface into buffered tiles
        if i < tile_size_x:
            buffer_x_start = 0
            buffer_x_length = (
                2 * tile_size_x
                if (2 * tile_size_x) < (xsize - buffer_x_start)
                else xsize - buffer_x_start
            )
        else:
            buffer_x_start = i - tile_size_x
            buffer_x_length = (
                3 * tile_size_x
                if (3 * tile_size_x) < (xsize - buffer_x_start)
                else xsize - buffer_x_start
            )

        if j < tile_size_y:
            buffer_y_start = 0
            buffer_y_length = (
                2 * tile_size_y
                if (2 * tile_size_y) < (ysize - buffer_y_start)
                else ysize - buffer_y_start
            )
        else:
            buffer_y_start = j - tile_size_y
            buffer_y_length = (
                3 * tile_size_y
                if (3 * tile_size_y) < (ysize - buffer_y_start)
                else ysize - buffer_y_start
            )

        buffered_tile_raster_path = (
            tile_folder / f"{cost_surface_raster.stem}_tile_buffer_{i}_{j}.tif"
        )

        buffer_com_string = f"gdal_translate -of GTIFF -srcwin {buffer_x_start}, {buffer_y_start}, {buffer_x_length}, {buffer_y_length} {cost_surface_raster} {buffered_tile_raster_path}"
        os.system(buffer_com_string)

        # Get raster metadata for export
        buffered_tile_raster = rasterio.open(buffered_tile_raster_path)
        kwargs = buffered_tile_raster.meta
        kwargs.update(
            dtype=current_dtype, nodata=current_nodata, count=1, compress="lzw"
        )

        tile_raster_info = pygeoprocessing.get_raster_info(
            str(buffered_tile_raster_path)
        )
        base_args = {
            "base_array": "",
            "target_nodata": current_nodata,
            "pixel_size": tile_raster_info["pixel_size"],
            "origin": (
                tile_raster_info["bounding_box"][0],
                tile_raster_info["bounding_box"][3],
            ),
            "projection_wkt": tile_raster_info["projection_wkt"],
            "target_path": "",
        }

        tile_array = buffered_tile_raster.read(1)

        # Create borders around buffered tiles
        tile_array.fill(current_nodata)

        # Westline
        westline_raster = tile_folder / westline_name.format(i, j)
        line_array = tile_array.copy().astype(current_dtype)
        line_array[:, 0] = current_value
        with rasterio.open(westline_raster, "w", **kwargs) as dst:
            dst.write_band(1, line_array)

        # Eastline
        eastline_raster = tile_folder / eastline_name.format(i, j)
        line_array = tile_array.copy().astype(current_dtype)
        line_array[:, -1] = current_value
        with rasterio.open(eastline_raster, "w", **kwargs) as dst:
            dst.write_band(1, line_array)

        # Northline
        northline_raster = tile_folder / northline_name.format(i, j)
        line_array = tile_array.copy().astype(current_dtype)
        line_array[0] = current_value
        with rasterio.open(northline_raster, "w", **kwargs) as dst:
            dst.write_band(1, line_array)

        # Southline
        southline_raster = tile_folder / southline_name.format(i, j)
        line_array = tile_array.copy().astype(current_dtype)
        line_array[-1] = current_value
        with rasterio.open(southline_raster, "w", **kwargs) as dst:
            dst.write_band(1, line_array)

        # Iterate through each directional run and run circuitscape
        for run_name, source_raster, ground_raster in zip(
            directions,
            [westline_raster, eastline_raster, northline_raster, southline_raster],
            [
                eastline_raster,
                westline_raster,
                southline_raster,
                northline_raster,
            ],
        ):

            # run_name, source_raster, ground_raster = "we", westline_raster, eastline_raster

            # Replace habitat, current, and ground rasters in new ini file with buffered tile, current, and ground rasters, and change output locations

            run_ini_file = tile_folder / f"{run_name}.ini"

            config = configparser.ConfigParser()
            config.read(seed_ini)

            config.set(
                section="Habitat raster or graph",
                option="habitat_file",
                value=str(buffered_tile_raster_path).replace("\\", r"/"),
            )

            config.set(
                section="Options for advanced mode",
                option="source_file",
                value=str(source_raster).replace("\\", r"/"),
            )

            config.set(
                section="Options for advanced mode",
                option="ground_file",
                value=str(ground_raster).replace("\\", r"/"),
            )

            config.set(
                section="Output options",
                option="output_file",
                value=str(run_ini_file.with_suffix(".out")).replace("\\", r"/"),
            )

            # # Create new .ini file in tile folder
            with open(run_ini_file, "w") as configfile:
                config.write(configfile)


def _run_circuitscape(workspace_path: pathlike):
    os.system(
        f"julia '{Path(__file__).parent / 'circuitscape_runs.jl'}' {workspace_path}"
    )


def _process_circuitscape_outputs(
    cost_surface_raster: pathlike, workspace_path: pathlike
):

    # Ensure path compliance
    cost_surface_raster = Path(cost_surface_raster)
    workspace_path = Path(workspace_path)

    # Set directions
    directions = [
        "we",
        "ew",
        "ns",
        "sn",
    ]

    # Iterate through tile folders
    omnidirectional_tile_raster_paths = []
    for tile_folder in tqdm(
        workspace_path.iterdir(), desc="Processing tiles", unit="tile"
    ):
        if not tile_folder.is_dir():
            continue

        # Get tile coordinates
        i, j = tile_folder.name.split("_")

        directional_current_rasters = []

        # Iterate through directions from Circuitscape runs
        for direction in directions:

            tile_raster_path = (
                tile_folder / f"{cost_surface_raster.stem}_tile_{i}_{j}.tif"
            )
            tile_raster_info = pygeoprocessing.get_raster_info(str(tile_raster_path))

            current_raster_path = tile_folder / f"{direction}_curmap.asc"

            clipped_current_raster_path = tile_folder / f"{direction}_curmap.tif"

            # Clip buffered current raster to tile
            pygeoprocessing.warp_raster(
                str(current_raster_path),
                tile_raster_info["pixel_size"],
                str(clipped_current_raster_path),
                "near",
                target_bb=tile_raster_info["bounding_box"],
            )
            directional_current_rasters.append(clipped_current_raster_path)

        # Merge all directional outputs into average 'omnidirectional' raster
        omnidirectional_raster_path = tile_folder / f"omnidirectional_curmap.tif"

        def mean_op(*array_list):
            """Mean operation for raster calculator."""
            result = np.mean(array_list, axis=0)
            return result

        pygeoprocessing.raster_map(
            mean_op,
            [str(r) for r in directional_current_rasters],
            str(omnidirectional_raster_path),
        )

        omnidirectional_tile_raster_paths.append(omnidirectional_raster_path)

    # Mosaic all omnidirectional tile outputs into a single raster
    logger.info(
        f"Mosaicking {len(omnidirectional_tile_raster_paths)} omnidirectional rasters"
    )
    output_current_raster_path = workspace_path / "omnidirectional_curmap.tif"

    rasters_to_mosaic = [rasterio.open(p) for p in omnidirectional_tile_raster_paths]
    mosaic, output_transform = rasterio.merge.merge(
        rasters_to_mosaic, nodata=TARGET_NODATA
    )
    output_profile = rasters_to_mosaic[0].profile.copy()
    output_profile.update(
        driver="GTiff",
        nodata=TARGET_NODATA,
        height=mosaic.shape[1],
        width=mosaic.shape[2],
        transform=output_transform,
        compress="LZW",
    )
    with rasterio.open(output_current_raster_path, "w", **output_profile) as m:
        m.write(mosaic)


def execute(
    cost_surface_raster: pathlike,
    seed_ini: pathlike,
    workspace_path: pathlike,
    tile_size_x=500,
    tile_size_y=500,
    keep_intermediates=False,
):
    """Run Circuitscape on a cost surface raster.

    Parameters
    ----------
    cost_surface_raster : pathlib.Path
        Path to the cost surface raster.
    seed_ini : pathlib.Path
        Path to the seed Circuitscape .ini file.
    workspace_path : pathlib.Path
        Path to the workspace folder where output files will be saved.
    tile_size_x : int, optional
        Width of tiles in pixels, by default 500.
    tile_size_y : int, optional
        Height of tiles in pixels, by default 500.

    Returns
    -------
    None
    """

    # Ensure path compliance
    cost_surface_raster = Path(cost_surface_raster)
    seed_ini = Path(seed_ini)
    workspace_path = Path(workspace_path)
    workspace_path.mkdir(exist_ok=True)

    logger.info(f"Processing Circuitscape inputs for {cost_surface_raster.name}")
    _process_circuitscape_inputs(
        cost_surface_raster, seed_ini, workspace_path, tile_size_x, tile_size_y
    )

    logger.info(f"Running Circuitscape for {cost_surface_raster.name}")
    _run_circuitscape(workspace_path)

    logger.info(f"Processing Circuitscape outputs for {cost_surface_raster.name}")
    _process_circuitscape_outputs(cost_surface_raster, workspace_path)

    # Delete all tile folders, if requested
    if not keep_intermediates:
        for tile_folder in workspace_path.iterdir():
            if tile_folder.is_dir():
                shutil.rmtree(tile_folder)


# # Testing

# gis_folder = Path(r"/Users/cnootenboom/Documents/Projects/Circuitscape")

# cost_surface_raster = gis_folder / "cost_surface.tif"
# workspace_path = gis_folder / "circuitscape"
# seed_ini = gis_folder / "circuitscape/blank_circuitscape_ini.ini"

# circuitscape(
#     cost_surface_raster,
#     seed_ini,
#     workspace_path,
# )
