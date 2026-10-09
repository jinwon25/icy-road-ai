"""제공 GeoTIFF의 명시적 수평 기준계로 원시 표고·상대 지형을 추출한다."""
from __future__ import annotations

import numpy as np
import tifffile
from pyproj import CRS, Transformer
from pyproj.crs import ProjectedCRS
from pyproj.crs.coordinate_operation import TransverseMercatorConversion


class DemSampler:
    def __init__(self, path):
        with tifffile.TiffFile(path) as tif:
            tags = tif.pages[0].tags
            self.scale = tuple(tags[33550].value)
            tie = tags[33922].value
            self.x0, self.y0 = tie[3] - tie[0] * self.scale[0], tie[4] + tie[1] * self.scale[1]
            self.nodata = float(tags[42113].value)
            directory = tags[34735].value
            doubles = tags[34736].value
            keys = {}
            for i in range(directory[3]):
                code, source, count, value = directory[4 + i * 4:8 + i * 4]
                if source == 0:
                    keys[code] = value
                elif source == 34736 and count == 1:
                    keys[code] = doubles[value]
            if keys.get(2050) != 6656 or keys.get(3075) != 1 or keys.get(3076) != 9001 or keys.get(1025) != 1:
                raise ValueError("Expected ITRF2000, Transverse Mercator, metre axes, PixelIsArea")
            self.crs = ProjectedCRS(name="Supplied ITRF2000 Transverse Mercator",
                                    geodetic_crs=CRS.from_epsg(8997),
                                    conversion=TransverseMercatorConversion(
                                        latitude_natural_origin=keys[3081], longitude_natural_origin=keys[3080],
                                        false_easting=keys[3082], false_northing=keys[3083],
                                        scale_factor_natural_origin=keys[3092]))
            self.vertical_unit = keys.get(4099)
        self.grid = tifffile.memmap(path)
        self.transformer = Transformer.from_crs("EPSG:5179", self.crs, always_xy=True)

    def at_projected_point(self, x, y, radius_m=500.):
        x, y = self.transformer.transform(x, y)
        col, row = int(np.floor((x - self.x0) / self.scale[0])), int(np.floor((self.y0 - y) / self.scale[1]))
        height, width = self.grid.shape
        empty = {"dem_value": np.nan, "dem_relative_500": np.nan, "dem_percentile_500": np.nan,
                 "dem_valid_fraction_500": 0.}
        if not (0 <= row < height and 0 <= col < width):
            return empty
        nr, nc = int(np.ceil(radius_m / self.scale[1])), int(np.ceil(radius_m / self.scale[0]))
        r0, r1 = max(0, row - nr), min(height, row + nr + 1)
        c0, c1 = max(0, col - nc), min(width, col + nc + 1)
        patch = np.asarray(self.grid[r0:r1, c0:c1])
        yy, xx = np.mgrid[r0:r1, c0:c1]
        circle = ((xx - col) * self.scale[0]) ** 2 + ((yy - row) * self.scale[1]) ** 2 <= radius_m ** 2
        good = circle & np.isfinite(patch) & ~np.isclose(patch, self.nodata)
        values = patch[good]
        value = float(self.grid[row, col])
        fraction = float(good.sum() / circle.sum())
        if not np.isfinite(value) or np.isclose(value, self.nodata) or not len(values):
            return {**empty, "dem_valid_fraction_500": fraction}
        return {"dem_value": value, "dem_relative_500": value - float(np.median(values)),
                "dem_percentile_500": float(((values < value).sum() + .5 * (values == value).sum()) / len(values)),
                "dem_valid_fraction_500": fraction}


def curvature_proxy(line, spacing_m=50.):
    """중심선의 세 점 외접원 곡률. 공식 설계 반경·방향·경사와 구별한다."""
    if spacing_m <= 0:
        raise ValueError("Positive spacing required")
    if line.length < 2 * spacing_m:
        return {"curvature_p90_inv_m": np.nan, "curvature_samples": 0}
    positions = np.arange(0, line.length + .001, spacing_m)
    points = np.array([[line.interpolate(d).x, line.interpolate(d).y] for d in positions])
    a, b, c = points[:-2], points[1:-1], points[2:]
    ab, bc, ac = b - a, c - b, c - a
    cross = np.abs(ab[:, 0] * ac[:, 1] - ab[:, 1] * ac[:, 0])
    denominator = np.linalg.norm(ab, axis=1) * np.linalg.norm(bc, axis=1) * np.linalg.norm(ac, axis=1)
    values = np.divide(2 * cross, denominator, out=np.full(len(cross), np.nan), where=denominator > 0)
    values = values[np.isfinite(values)]
    return {"curvature_p90_inv_m": float(np.quantile(values, .9)) if len(values) else np.nan,
            "curvature_samples": len(values)}
