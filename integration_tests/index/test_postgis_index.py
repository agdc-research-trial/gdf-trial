# This file is part of the Open Data Cube, see https://opendatacube.org for more information
#
# Copyright (c) 2015-2022 ODC Contributors
# SPDX-License-Identifier: Apache-2.0
import pytest
from uuid import uuid4 as random_uuid

from datacube.model import LineageDirection, Range
from datacube.index import Index
from datacube.utils.geometry import CRS


@pytest.mark.parametrize('datacube_env_name', ('experimental',))
def test_create_spatial_index(index: Index):
    # Default spatial index for 4326
    assert list(index.spatial_indexes()) == [CRS("EPSG:4326")]
    # WKT CRS which cannot be mapped to an EPSG number.
    assert not index.create_spatial_index(CRS(
        'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137,298.257223563]]'
        ',PRIMEM["Weird",22.3],UNIT["Degree",0.017453292519943295]]'
    ))
    assert list(index.spatial_indexes()) == [CRS("EPSG:4326")]
    assert index.create_spatial_index(CRS("EPSG:3577"))
    assert index.create_spatial_index(CRS("WGS-84"))
    assert set(index.spatial_indexes(refresh=True)) == {CRS("EPSG:3577"), CRS("EPSG:4326")}


@pytest.mark.parametrize('datacube_env_name', ('experimental',))
def test_spatial_index_maintain(index: Index, ls8_eo3_product, eo3_ls8_dataset_doc):
    index.create_spatial_index(CRS("EPSG:3577"))
    assert set(index.spatial_indexes(refresh=True)) == {CRS("EPSG:3577"), CRS("EPSG:4326")}
    from datacube.index.hl import Doc2Dataset
    resolver = Doc2Dataset(index, products=[ls8_eo3_product.name], verify_lineage=False)
    ds, err = resolver(*eo3_ls8_dataset_doc)
    assert err is None and ds is not None
    ds = index.datasets.add(ds, False)
    assert ds
    index.datasets.archive([ds.id])
    index.datasets.purge([ds.id])
    # Can't really read yet, but seems to write at least


@pytest.mark.parametrize('datacube_env_name', ('experimental',))
def test_spatial_index_populate(index: Index,
                                ls8_eo3_product,
                                wo_eo3_product,
                                ls8_eo3_dataset, ls8_eo3_dataset2,
                                ls8_eo3_dataset3, ls8_eo3_dataset4,
                                wo_eo3_dataset):
    index.create_spatial_index(CRS("EPSG:3577"))
    assert set(index.spatial_indexes(refresh=True)) == {CRS("EPSG:3577"), CRS("EPSG:4326")}
    assert index.update_spatial_index(
        crses=[CRS("EPSG:4326")],
        dataset_ids=[ls8_eo3_dataset.id, ls8_eo3_dataset2.id]
    ) == 2
    assert index.update_spatial_index(product_names=[ls8_eo3_product.name]) == 8
    assert index.update_spatial_index() == 10
    assert index.update_spatial_index(
        crses=[CRS("EPSG:4326")],
        product_names=[wo_eo3_product.name],
        dataset_ids=[ls8_eo3_dataset.id]
    ) == 2
    assert index.update_spatial_index(product_names=[ls8_eo3_product.name], dataset_ids=[ls8_eo3_dataset.id]) == 8


@pytest.mark.parametrize('datacube_env_name', ('experimental',))
def test_spatial_index_crs_validity(index: Index,
                                    ls8_eo3_product, ls8_eo3_dataset,
                                    africa_s2_eo3_product, africa_eo3_dataset):
    epsg4326 = CRS("EPSG:4326")
    epsg3577 = CRS("EPSG:3577")
    index.create_spatial_index(epsg3577)
    assert set(index.spatial_indexes(refresh=True)) == {epsg4326, epsg3577}
    assert index.update_spatial_index(crses=[epsg3577]) == 2


def test_spatial_index_crs_sanitise():
    epsg4326 = CRS("EPSG:4326")
    epsg3577 = CRS("EPSG:3577")
    from datacube.utils.geometry import polygon
    # EPSG:4326 polygons to be converted in EPSG:3577
    # Equal to entire valid region
    entire = polygon((
        (112.85, -43.7),
        (112.85, -9.86),
        (153.69, -9.86),
        (153.69, -43.7),
        (112.85, -43.7)), crs=epsg4326)
    # inside valid region
    valid = polygon((
        (130.15, -25.7),
        (130.15, -19.86),
        (135.22, -19.86),
        (135.22, -25.7),
        (130.15, -25.7)), crs=epsg4326)
    # completely outside valid region
    invalid = polygon((
        (-10.15, 25.7),
        (-10.15, 33.86),
        (5.22, 33.86),
        (5.22, 25.7),
        (-10.15, 25.7)), crs=epsg4326)
    # intersects valid region
    partial = polygon((
        (103.15, -25.7),
        (103.15, -19.86),
        (135.22, -19.86),
        (135.22, -25.7),
        (103.15, -25.7)), crs=epsg4326)
    from datacube.drivers.postgis._spatial import sanitise_extent

    assert sanitise_extent(entire, epsg3577) == entire.to_crs("EPSG:3577")
    assert sanitise_extent(valid, epsg3577) == valid.to_crs("EPSG:3577")
    assert sanitise_extent(invalid, epsg3577) is None
    assert sanitise_extent(partial, epsg3577).area < partial.to_crs("EPSG:3577").area
    assert sanitise_extent(entire, epsg4326) == entire.to_crs("EPSG:4326")


@pytest.mark.parametrize('datacube_env_name', ('experimental',))
def test_spatial_extent(index,
                        ls8_eo3_dataset, ls8_eo3_dataset2,
                        ls8_eo3_dataset3, ls8_eo3_dataset4,
                        africa_s2_eo3_product, africa_eo3_dataset):
    epsg4326 = CRS("EPSG:4326")
    epsg3577 = CRS("EPSG:3577")
    index.create_spatial_index(epsg3577)
    index.update_spatial_index(crses=[epsg3577])
    ext1 = index.datasets.spatial_extent([ls8_eo3_dataset.id], epsg4326)
    ext2 = index.datasets.spatial_extent([ls8_eo3_dataset2.id], epsg4326)
    ext12 = index.datasets.spatial_extent([ls8_eo3_dataset.id, ls8_eo3_dataset2.id], epsg4326)
    assert ext1 is not None and ext2 is not None and ext12 is not None
    assert ext1 == ext2
    assert ext12.difference(ext1).area < 0.001
    assert ls8_eo3_dataset.extent.to_crs(epsg4326).intersects(ext1)
    assert ls8_eo3_dataset.extent.to_crs(epsg4326).intersects(ext12)
    assert ls8_eo3_dataset2.extent.to_crs(epsg4326).intersects(ext2)
    assert ls8_eo3_dataset2.extent.to_crs(epsg4326).intersects(ext12)
    extau12 = index.datasets.spatial_extent([ls8_eo3_dataset.id, ls8_eo3_dataset2.id], epsg3577)
    extau12africa = index.datasets.spatial_extent(
        [ls8_eo3_dataset.id, ls8_eo3_dataset2.id, africa_eo3_dataset.id],
        epsg3577
    )
    assert extau12 == extau12africa
    ext3 = index.datasets.spatial_extent([ls8_eo3_dataset3.id], epsg4326)
    ext1234 = index.datasets.spatial_extent(
        [
            ls8_eo3_dataset.id, ls8_eo3_dataset2.id,
            ls8_eo3_dataset3.id, ls8_eo3_dataset4.id
        ], epsg4326)
    assert ext1.difference(ext1234).area < 0.001
    assert ext3.difference(ext1234).area < 0.001
    ext1_3577 = index.datasets.spatial_extent([ls8_eo3_dataset.id], epsg3577)
    assert ext1_3577.intersects(ls8_eo3_dataset.extent._to_crs(epsg3577))


@pytest.mark.parametrize('datacube_env_name', ('experimental',))
def test_spatial_search(index,
                        ls8_eo3_dataset, ls8_eo3_dataset2,
                        ls8_eo3_dataset3, ls8_eo3_dataset4):
    epsg4326 = CRS("EPSG:4326")
    epsg3577 = CRS("EPSG:3577")
    index.create_spatial_index(epsg3577)
    index.update_spatial_index(crses=[epsg3577])
    # Test old style lat/lon search
    dss = index.datasets.search_eager(
        product=ls8_eo3_dataset.product.name,
        lat=Range(begin=-37.5, end=37.0),
        lon=Range(begin=148.5, end=149.0)
    )
    dssids = [ds.id for ds in dss]
    assert len(dssids) == 2
    assert ls8_eo3_dataset.id in dssids
    assert ls8_eo3_dataset2.id in dssids
    # Test polygons
    exact1_4326 = ls8_eo3_dataset.extent.to_crs(epsg4326)
    exact1_3577 = ls8_eo3_dataset.extent.to_crs(epsg3577)
    exact3_4326 = ls8_eo3_dataset3.extent.to_crs(epsg4326)
    exact3_3577 = ls8_eo3_dataset3.extent.to_crs(epsg3577)
    dssids = set(ds.id for ds in index.datasets.search(product=ls8_eo3_dataset.product.name, geometry=exact1_4326))
    assert len(dssids) == 2
    assert ls8_eo3_dataset.id in dssids
    assert ls8_eo3_dataset2.id in dssids
    dssids = [ds.id for ds in index.datasets.search(product=ls8_eo3_dataset.product.name, geometry=exact1_3577)]
    assert len(dssids) == 2
    assert ls8_eo3_dataset.id in dssids
    assert ls8_eo3_dataset2.id in dssids
    dssids = [ds.id for ds in index.datasets.search(product=ls8_eo3_dataset.product.name, geometry=exact3_4326)]
    assert len(dssids) == 2
    assert ls8_eo3_dataset3.id in dssids
    assert ls8_eo3_dataset3.id in dssids
    dssids = [ds.id for ds in index.datasets.search(product=ls8_eo3_dataset.product.name, geometry=exact3_3577)]
    assert len(dssids) == 2
    assert ls8_eo3_dataset3.id in dssids
    assert ls8_eo3_dataset3.id in dssids


@pytest.mark.parametrize('datacube_env_name', ('experimental',))
def test_lineage_home_api(index):
    a_uuids = [random_uuid() for i in range(10)]
    b_uuids = [random_uuid() for i in range(10)]
    all_uuids = a_uuids + b_uuids
    assert index.lineage.get_homes(*a_uuids) == {}
    # Test delete of non-existent entries
    assert index.lineage.clear_home(*a_uuids) == 0
    # Test insert a uuids
    assert index.lineage.set_home("spam", *a_uuids) == 10
    for home in index.lineage.get_homes(*a_uuids).values():
        assert home == "spam"
    # Test update with and without allow_update
    index.lineage.set_home("eggs", *a_uuids) == 0
    index.lineage.set_home("eggs", *a_uuids, allow_updates=True) == 10
    for home in index.lineage.get_homes(*a_uuids).values():
        assert home == "eggs"
    assert index.lineage.get_homes(*b_uuids) == {}
    index.lineage.set_home("eggs", *a_uuids, allow_updates=True) == 0
    index.lineage.set_home("eggs", *b_uuids, allow_updates=True) == 10

    # Test clear_home with actual work done.
    assert index.lineage.clear_home(*a_uuids) == 10
    assert index.lineage.clear_home(*b_uuids) == 10


@pytest.mark.parametrize('datacube_env_name', ('experimental',))
def test_lineage_tree_index_api(index, src_lineage_tree, src_tree_ids):
    src_tree = index.lineage.get_source_tree(src_tree_ids["root"])
    assert src_tree.dataset_id == src_tree_ids["root"]
    assert src_tree.direction == LineageDirection.SOURCES
    assert src_tree.children == {}
    index.lineage.add(src_lineage_tree, max_depth=1)
    src_tree = index.lineage.get_source_tree(src_tree_ids["root"])
    assert src_tree.dataset_id == src_tree_ids["root"]
    assert src_tree.direction == LineageDirection.SOURCES
    for ard_subtree in src_tree.children["ard"]:
        assert ard_subtree.dataset_id in (src_tree_ids["ard1"], src_tree_ids["ard2"])
        assert not ard_subtree.children
