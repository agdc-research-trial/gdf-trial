# This file is part of the Open Data Cube, see https://opendatacube.org for more information
#
# Copyright (c) 2015-2025 ODC Contributors
# SPDX-License-Identifier: Apache-2.0
import numpy as np

import pytest
from rasterio.enums import Resampling

from datacube.storage._read import (
    read_time_slice,
    read_time_slice_v2,
    pick_read_scale,
    rdr_geobox)

from datacube.testutils.io import RasterFileDataSource
from odc.geo.overlap import compute_reproject_roi
from odc.geo.roi import roi_shape, roi_is_empty
from odc.geo.geobox import GeoBox

from odc.geo import geobox as gbx

from datacube.testutils.io import (
    rio_slurp
)

from datacube.testutils.geom import (
    epsg3857,
    AlbersGS,
)


nearest_resampling_parametrize = pytest.mark.parametrize(
    "nearest_resampling", ['nearest', Resampling.nearest, Resampling.nearest.value]
)


def test_pick_read_scale():
    assert pick_read_scale(0.7) == 1
    assert pick_read_scale(1.3) == 1
    assert pick_read_scale(2.3) == 2
    assert pick_read_scale(1.99999) == 2


@nearest_resampling_parametrize
def test_read_paste(nearest_resampling, tmpdir):
    from datacube.testutils import mk_test_image
    from datacube.testutils.io import write_gtiff
    from pathlib import Path

    pp = Path(str(tmpdir))

    xx = mk_test_image(128, 64, nodata=None)
    assert (xx != -999).all()

    mm = write_gtiff(pp/'tst-read-paste-128x64-int16.tif', xx, nodata=None)

    def _read(geobox, resampling=nearest_resampling,
              fallback_nodata=-999,
              dst_nodata=-999,
              check_paste=False):
        with RasterFileDataSource(mm.path, 1, nodata=fallback_nodata).open() as rdr:
            if check_paste:
                # check that we are using paste
                rr = compute_reproject_roi(rdr_geobox(rdr), geobox)
                assert rr.paste_ok is True

            yy = np.full(geobox.shape, dst_nodata, dtype=rdr.dtype)
            roi = read_time_slice(rdr, yy, geobox, resampling, dst_nodata)
            return yy, roi

    # read native whole
    yy, roi = _read(mm.geobox)
    np.testing.assert_array_equal(xx, yy)
    assert roi == np.s_[0:64, 0:128]

    # read native whole, no nodata case
    yy, roi = _read(mm.geobox, fallback_nodata=None)
    np.testing.assert_array_equal(xx, yy)
    assert roi == np.s_[0:64, 0:128]

    # read native whole, ignoring small sub-pixel translation
    yy, roi = _read(gbx.translate_pix(mm.geobox, 0.3, -0.4), fallback_nodata=-33)
    np.testing.assert_array_equal(xx, yy)
    assert roi == np.s_[0:64, 0:128]

    # no overlap between src and dst
    yy, roi = _read(gbx.translate_pix(mm.geobox, 10000, -10000))
    assert roi_is_empty(roi)

    # read with Y flipped
    yy, roi = _read(gbx.flipy(mm.geobox))
    np.testing.assert_array_equal(xx[::-1, :], yy)
    assert roi == np.s_[0:64, 0:128]

    # read with X flipped
    yy, roi = _read(gbx.flipx(mm.geobox))
    np.testing.assert_array_equal(xx[:, ::-1], yy)
    assert roi == np.s_[0:64, 0:128]

    # read with X and Y flipped
    yy, roi = _read(gbx.flipy(gbx.flipx(mm.geobox)))
    assert roi == np.s_[0:64, 0:128]
    np.testing.assert_array_equal(xx[::-1, ::-1], yy[roi])

    # dst is fully inside src
    sroi = np.s_[10:19, 31:47]
    yy, roi = _read(mm.geobox[sroi])
    np.testing.assert_array_equal(xx[sroi], yy[roi])

    # partial overlap
    yy, roi = _read(gbx.translate_pix(mm.geobox, -3, -10))
    assert roi == np.s_[10:64, 3:128]
    np.testing.assert_array_equal(xx[:-10, :-3], yy[roi])
    assert (yy[:10, :] == -999).all()
    assert (yy[:, :3] == -999).all()

    # scaling paste
    yy, roi = _read(gbx.zoom_out(mm.geobox, 2), check_paste=True)
    assert roi == np.s_[0:32, 0:64]
    np.testing.assert_array_equal(xx[1::2, 1::2], yy)


@nearest_resampling_parametrize
def test_read_with_reproject(nearest_resampling, tmpdir):
    from datacube.testutils import mk_test_image
    from datacube.testutils.io import write_gtiff
    from pathlib import Path

    pp = Path(str(tmpdir))

    xx = mk_test_image(128, 64, nodata=None)
    assert (xx != -999).all()
    tile = AlbersGS.tile_geobox((17, -40))[:64, :128]

    mm = write_gtiff(pp/'tst-read-with-reproject-128x64-int16.tif', xx,
                     crs=str(tile.crs),
                     resolution=tile.resolution.xy,
                     offset=tile.transform*(0, 0),
                     nodata=-999)
    assert mm.geobox == tile

    def _read(geobox,
              resampling=nearest_resampling,
              fallback_nodata=None,
              dst_nodata=-999):
        with RasterFileDataSource(mm.path, 1, nodata=fallback_nodata).open() as rdr:
            yy = np.full(geobox.shape, dst_nodata, dtype=rdr.dtype)
            roi = read_time_slice(rdr, yy, geobox, resampling, dst_nodata)
            return yy, roi

    geobox = gbx.pad(mm.geobox, 10)
    geobox = gbx.zoom_out(geobox, 0.873)
    yy, roi = _read(geobox)

    assert roi[0].start > 0 and roi[1].start > 0
    assert (yy[0] == -999).all()

    yy_expect, _ = rio_slurp(mm.path, geobox)
    np.testing.assert_array_equal(yy, yy_expect)

    geobox = gbx.zoom_out(mm.geobox[3:-3, 10:-10], 2.1)
    yy, roi = _read(geobox)

    assert roi_shape(roi) == geobox.shape
    assert not (yy == -999).any()

    geobox = GeoBox.from_geopolygon(mm.geobox.extent.to_crs(epsg3857).buffer(50),
                                    resolution=mm.geobox.resolution)

    assert geobox.extent.contains(mm.geobox.extent.to_crs(epsg3857))
    assert geobox.crs != mm.geobox.crs
    yy, roi = _read(geobox)
    assert roi[0].start > 0 and roi[1].start > 0
    assert (yy[0] == -999).all()

    geobox = gbx.zoom_out(geobox, 4)
    yy, roi = _read(geobox, resampling='average')
    nvalid = (yy != -999).sum()
    nempty = (yy == -999).sum()
    assert nvalid > nempty


@nearest_resampling_parametrize
def test_read_paste_v2(nearest_resampling, tmpdir):
    from datacube.testutils import mk_test_image
    from datacube.testutils.io import write_gtiff
    from datacube.testutils.iodriver import open_reader
    from pathlib import Path

    pp = Path(str(tmpdir))

    xx = mk_test_image(128, 64, nodata=None)
    assert (xx != -999).all()

    mm = write_gtiff(pp/'tst-read-paste-128x64-int16.tif', xx, nodata=None)

    def _read(geobox, resampling=nearest_resampling,
              fallback_nodata=-999,
              dst_nodata=-999,
              check_paste=False):

        rdr = open_reader(mm.path,
                          nodata=fallback_nodata)
        if check_paste:
            # check that we are using paste
            rr = compute_reproject_roi(rdr_geobox(rdr), geobox)
            assert rr.paste_ok is True

        yy = np.full(geobox.shape, dst_nodata, dtype=rdr.dtype)
        yy_, roi = read_time_slice_v2(rdr, geobox, resampling, dst_nodata)
        if yy_ is None:
            print(f"Got None out of read_time_slice_v2: {roi} must be empty")
        else:
            yy[roi] = yy_
        return yy, roi

    # read native whole
    yy, roi = _read(mm.geobox)
    np.testing.assert_array_equal(xx, yy)
    assert roi == np.s_[0:64, 0:128]

    # read native whole, no nodata case
    yy, roi = _read(mm.geobox, fallback_nodata=None)
    np.testing.assert_array_equal(xx, yy)
    assert roi == np.s_[0:64, 0:128]

    # read native whole, ignoring small sub-pixel translation
    yy, roi = _read(gbx.translate_pix(mm.geobox, 0.3, -0.4), fallback_nodata=-33)
    np.testing.assert_array_equal(xx, yy)
    assert roi == np.s_[0:64, 0:128]

    # no overlap between src and dst
    yy, roi = _read(gbx.translate_pix(mm.geobox, 10000, -10000))
    assert roi_is_empty(roi)

    # read with Y flipped
    yy, roi = _read(gbx.flipy(mm.geobox))
    np.testing.assert_array_equal(xx[::-1, :], yy)
    assert roi == np.s_[0:64, 0:128]

    # read with X flipped
    yy, roi = _read(gbx.flipx(mm.geobox))
    np.testing.assert_array_equal(xx[:, ::-1], yy)
    assert roi == np.s_[0:64, 0:128]

    # read with X and Y flipped
    yy, roi = _read(gbx.flipy(gbx.flipx(mm.geobox)))
    assert roi == np.s_[0:64, 0:128]
    np.testing.assert_array_equal(xx[::-1, ::-1], yy[roi])

    # dst is fully inside src
    sroi = np.s_[10:19, 31:47]
    yy, roi = _read(mm.geobox[sroi])
    np.testing.assert_array_equal(xx[sroi], yy[roi])

    # partial overlap
    yy, roi = _read(gbx.translate_pix(mm.geobox, -3, -10))
    assert roi == np.s_[10:64, 3:128]
    np.testing.assert_array_equal(xx[:-10, :-3], yy[roi])
    assert (yy[:10, :] == -999).all()
    assert (yy[:, :3] == -999).all()

    # scaling paste
    yy, roi = _read(gbx.zoom_out(mm.geobox, 2), check_paste=True)
    assert roi == np.s_[0:32, 0:64]
    np.testing.assert_array_equal(xx[1::2, 1::2], yy)


@nearest_resampling_parametrize
def test_read_with_reproject_v2(nearest_resampling, tmpdir):
    from datacube.testutils import mk_test_image
    from datacube.testutils.io import write_gtiff
    from datacube.testutils.iodriver import open_reader
    from pathlib import Path

    pp = Path(str(tmpdir))

    xx = mk_test_image(128, 64, nodata=None)
    assert (xx != -999).all()
    tile = AlbersGS.tile_geobox((17, -40))[:64, :128]

    def _read(geobox, resampling=nearest_resampling,
              fallback_nodata=-999,
              dst_nodata=-999):

        rdr = open_reader(mm.path,
                          nodata=fallback_nodata)

        yy = np.full(geobox.shape, dst_nodata, dtype=rdr.dtype)
        yy_, roi = read_time_slice_v2(rdr, geobox, resampling, dst_nodata)
        yy[roi] = yy_
        return yy, roi

    mm = write_gtiff(pp/'tst-read-with-reproject-128x64-int16.tif', xx,
                     crs=str(tile.crs),
                     resolution=tile.resolution.xy,
                     offset=tile.transform*(0, 0),
                     nodata=-999)
    assert mm.geobox == tile

    geobox = gbx.pad(mm.geobox, 10)
    geobox = gbx.zoom_out(geobox, 0.873)
    yy, roi = _read(geobox)

    assert roi[0].start > 0 and roi[1].start > 0
    assert (yy[0] == -999).all()

    yy_expect, _ = rio_slurp(mm.path, geobox)
    np.testing.assert_array_equal(yy, yy_expect)

    geobox = gbx.zoom_out(mm.geobox[3:-3, 10:-10], 2.1)
    yy, roi = _read(geobox)

    assert roi_shape(roi) == geobox.shape
    assert not (yy == -999).any()

    geobox = GeoBox.from_geopolygon(mm.geobox.extent.to_crs(epsg3857).buffer(50),
                                    resolution=mm.geobox.resolution)

    assert geobox.extent.contains(mm.geobox.extent.to_crs(epsg3857))
    assert geobox.crs != mm.geobox.crs
    yy, roi = _read(geobox)
    assert roi[0].start > 0 and roi[1].start > 0
    assert (yy[0] == -999).all()

    geobox = gbx.zoom_out(geobox, 4)
    yy, roi = _read(geobox, resampling='average')
    nvalid = (yy != -999).sum()
    nempty = (yy == -999).sum()
    assert nvalid > nempty
