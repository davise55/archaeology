import pygeoprocessing

dem_raster_path = "data/least_cost_path_analysis/dem.tif"
dem_raster_info = pygeoprocessing.get_raster_info(dem_raster_path)

church_raster_path = "data/least_cost_path_analysis/churches.tif"

city_center_raster_path = "data/least_cost_path_analysis/city_center.tif"

# Create and burn church locations
pygeoprocessing.new_raster_from_base(
    dem_raster_path,
    church_raster_path,
    dem_raster_info["datatype"],
    [0],
)
pygeoprocessing.rasterize(
    "data/least_cost_path_analysis/least_cost_path.tif",
    "data/least_cost_path_analysis/least_cost_path_vectorized.tif",
    1,
)

# Create and burn city center
pygeoprocessing.new_raster_from_base(
    dem_raster_path,
    church_raster_path,
    dem_raster_info["datatype"],
    [0],
)
pygeoprocessing.rasterize(
    "data/least_cost_path_analysis/least_cost_path.tif",
    "data/least_cost_path_analysis/least_cost_path_vectorized.tif",
    1,
)
