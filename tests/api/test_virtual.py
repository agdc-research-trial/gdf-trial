from collections import OrderedDict
from datetime import datetime
from types import SimpleNamespace

import pytest
import mock
import numpy

from datacube.model import DatasetType, MetadataType, Dataset, GridSpec
from datacube.utils import geometry
from datacube.virtual import construct_from_yaml
from datacube.virtual.impl import Datacube
from datacube.virtual.utils import product_definitions_from_index


def example_metadata_type():
    return MetadataType(dict(name='eo',
                             dataset=dict(id=['id'],
                                          label=['ga_label'],
                                          creation_time=['creation_dt'],
                                          measurements=['image', 'bands'],
                                          grid_spatial=['grid_spatial', 'projection'],
                                          sources=['lineage', 'source_datasets'])),
                        dataset_search_fields={})


def example_product(name):
    blue = dict(name='blue', dtype='int16', nodata=-999, units='1')
    green = dict(name='green', dtype='int16', nodata=-999, units='1')
    flags = {"cloud_acca": {"bits": 10, "values": {"0": "cloud", "1": "no_cloud"}},
             "contiguous": {"bits": 8, "values": {"0": False, "1": True}},
             "cloud_fmask": {"bits": 11, "values": {"0": "cloud", "1": "no_cloud"}},
             "nir_saturated": {"bits": 3, "values": {"0": True, "1": False}},
             "red_saturated": {"bits": 2, "values": {"0": True, "1": False}},
             "blue_saturated": {"bits": 0, "values": {"0": True, "1": False}},
             "green_saturated": {"bits": 1, "values": {"0": True, "1": False}},
             "swir1_saturated": {"bits": 4, "values": {"0": True, "1": False}},
             "swir2_saturated": {"bits": 7, "values": {"0": True, "1": False}},
             "cloud_shadow_acca": {"bits": 12, "values": {"0": "cloud_shadow", "1": "no_cloud_shadow"}},
             "cloud_shadow_fmask": {"bits": 13, "values": {"0": "cloud_shadow", "1": "no_cloud_shadow"}}}

    pixelquality = dict(name='pixelquality', dtype='int16', nodata=0, units='1',
                        flags_definition=flags)

    result = DatasetType(example_metadata_type(),
                         dict(name=name, description="", metadata_type='eo', metadata={}))
    result.grid_spec = GridSpec(crs=geometry.CRS('EPSG:3577'),
                                tile_size=(100000., 100000.),
                                resolution=(-25, 25))
    if '_pq_' in name:
        result.definition = {'name': name, 'measurements': [pixelquality]}
    else:
        result.definition = {'name': name, 'measurements': [blue, green]}
    return result


def example_grid_spatial():
    return {
        "projection": {
            "valid_data": {
                "type": "Polygon",
                "coordinates": [[[1500000.0, -4000000.0],
                                 [1500000.0, -3900000.0],
                                 [1600000.0, -3900000.0],
                                 [1600000.0, -4000000.0],
                                 [1500000.0, -4000000.0]]]
            },
            "geo_ref_points": {
                "ll": {"x": 1500000.0, "y": -4000000.0},
                "lr": {"x": 1600000.0, "y": -4000000.0},
                "ul": {"x": 1500000.0, "y": -3900000.0},
                "ur": {"x": 1600000.0, "y": -3900000.0}
            },
            "spatial_reference": "EPSG:3577"
        }
    }


@pytest.fixture
def cloud_free_nbar():
    return construct_from_yaml("""
    collate:
      - transform: apply_mask
        mask_measurement_name: pixelquality
        input:
          &mask
          transform: make_mask
          flags:
              blue_saturated: false
              cloud_acca: no_cloud
              cloud_fmask: no_cloud
              cloud_shadow_acca: no_cloud_shadow
              cloud_shadow_fmask: no_cloud_shadow
              contiguous: true
              green_saturated: false
              nir_saturated: false
              red_saturated: false
              swir1_saturated: false
              swir2_saturated: false
          mask_measurement_name: pixelquality
          input:
            juxtapose:
              - product: ls8_nbar_albers
                measurements: ['blue', 'green']
              - product: ls8_pq_albers
      - transform: datacube.virtual.transformations.ApplyMask
        mask_measurement_name: pixelquality
        input:
          <<: *mask
          input:
            juxtapose:
              - product: ls7_nbar_albers
                measurements: ['blue', 'green']
              - product: ls7_pq_albers
    index_measurement_name: source_index
    """)


def load_data(*args, **kwargs):
    sources, geobox, measurements = args

    # this returns nodata bands which are good enough for this test
    result = Datacube.create_storage(OrderedDict((dim, sources.coords[dim]) for dim in sources.dims),
                                     geobox, measurements)
    return result


def group_datasets(*args, **kwargs):
    return Datacube.group_datasets(*args, **kwargs)


@pytest.fixture
def dc():
    result = mock.MagicMock()
    result.index.datasets.get_field_names.return_value = {'id', 'product', 'time'}

    ids = ['87a68652-b76a-450f-b44f-e5192243218e',
           'af9deddf-daf3-4e93-8f36-21437b52817c',
           '0c5d304f-7cd8-425e-8b0f-0f72b4fc4e6e',
           '9dcfc6f6-aa36-47ef-9501-177fa39e7e7d',
           'dda8b22e-27f5-40a5-99d4-b94810f545d0']

    def example_dataset(product, id, center_time):
        result = Dataset(example_product(product),
                         dict(id=id, grid_spatial=example_grid_spatial()),
                         uris=['file://test.zzz'])
        result.center_time = center_time
        return result

    def search(*args, **kwargs):
        product = kwargs['product']
        if product == 'ls8_nbar_albers':
            return [example_dataset(product, ids[0], datetime(2014, 2, 7, 23, 57, 26)),
                    example_dataset(product, ids[1], datetime(2014, 1, 1, 23, 57, 26))]
        elif product == 'ls8_pq_albers':
            return [example_dataset(product, ids[2], datetime(2014, 2, 7, 23, 57, 26))]
        elif product == 'ls7_nbar_albers':
            return [example_dataset(product, ids[3], datetime(2014, 1, 22, 23, 57, 36))]
        elif product == 'ls7_pq_albers':
            return [example_dataset(product, ids[4], datetime(2014, 1, 22, 23, 57, 36))]
        else:
            return []

    result.index.products.get_all = lambda: [example_product(x)
                                             for x in ['ls7_pq_albers',
                                                       'ls8_pq_albers',
                                                       'ls7_nbar_albers',
                                                       'ls8_nbar_albers']]
    result.index.products.get_by_name = example_product
    result.index.datasets.search = search
    return result


@pytest.fixture
def query():
    return {
        'time': ('2014-01-01', '2014-03-01'),
        'lat': (-35.2, -35.21),
        'lon': (149.0, 149.01)
    }


def test_name_resolution(cloud_free_nbar):
    for prod in cloud_free_nbar['collate']:
        assert callable(prod['transform'])


def test_str(cloud_free_nbar):
    assert str(cloud_free_nbar)


def test_output_measurements(cloud_free_nbar, dc):
    measurements = cloud_free_nbar.output_measurements(product_definitions_from_index(dc.index))
    assert 'blue' in measurements
    assert 'green' in measurements
    assert 'source_index' in measurements
    assert 'pixelquality' not in measurements


def test_group_datasets(cloud_free_nbar, dc, query):
    query_result = cloud_free_nbar.query(dc, **query)
    group = cloud_free_nbar.group(query_result, **query)

    time, _, _ = group.shape
    assert time == 2


def test_load_data(cloud_free_nbar, dc, query):
    with mock.patch('datacube.virtual.impl.Datacube') as mock_datacube:
        mock_datacube.load_data = load_data
        mock_datacube.group_datasets = group_datasets
        data = cloud_free_nbar.load(dc, **query)

    assert 'blue' in data
    assert 'green' in data
    assert 'source_index' in data
    assert 'pixelquality' not in data

    assert numpy.array_equal(numpy.unique(data.blue.values), numpy.array([-999]))
    assert numpy.array_equal(numpy.unique(data.green.values), numpy.array([-999]))
    assert numpy.array_equal(numpy.unique(data.source_index.values), numpy.array([0, 1]))


def test_rename(dc, query):
    rename = construct_from_yaml("""
        transform: rename
        measurement_names:
            green: verde
        input:
            product: ls8_nbar_albers
            measurements: [blue, green]
    """)

    with mock.patch('datacube.virtual.impl.Datacube') as mock_datacube:
        mock_datacube.load_data = load_data
        mock_datacube.group_datasets = group_datasets
        data = rename.load(dc, **query)

    assert 'verde' in data
    assert 'blue' in data
    assert 'green' not in data


def test_to_float(dc, query):
    to_float = construct_from_yaml("""
        transform: to_float
        input:
            product: ls8_nbar_albers
            measurements: [blue]
    """)

    with mock.patch('datacube.virtual.impl.Datacube') as mock_datacube:
        mock_datacube.load_data = load_data
        mock_datacube.group_datasets = group_datasets
        data = to_float.load(dc, **query)

    assert numpy.all(numpy.isnan(data.blue.values))
    assert data.blue.dtype == 'float32'
