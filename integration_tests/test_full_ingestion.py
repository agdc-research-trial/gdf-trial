from __future__ import absolute_import

import warnings
from datetime import datetime
from pathlib import Path

import six
import netCDF4
import numpy as np
import pytest

import yaml
from click.testing import CliRunner

import datacube.scripts.run_ingest
import datacube.scripts.agdc
from .conftest import LS5_NBAR_NAME, LS5_NBAR_ALBERS_NAME, EXAMPLE_LS5_DATASET_ID

PROJECT_ROOT = Path(__file__).parents[1]
CONFIG_SAMPLES = PROJECT_ROOT / 'docs/config_samples/'
LS5_SAMPLES = CONFIG_SAMPLES / 'ga_landsat_5/'
LS5_MATCH_RULES = CONFIG_SAMPLES / 'match_rules' / 'ls5_scenes.yaml'
LS5_NBAR_STORAGE_TYPE = LS5_SAMPLES / 'ls5_geographic.yaml'
LS5_NBAR_ALBERS_STORAGE_TYPE = LS5_SAMPLES / 'ls5_albers.yaml'

TEST_STORAGE_SHRINK_FACTOR = 100
TEST_STORAGE_NUM_MEASUREMENTS = 2
GEOGRAPHIC_VARS = ('latitude', 'longitude')
PROJECTED_VARS = ('x', 'y')

EXPECTED_STORAGE_UNIT_DATA_SHAPE = (1, 40, 40)
EXPECTED_NUMBER_OF_STORAGE_UNITS = 12

JSON_DATE_FORMAT = '%Y-%m-%dT%H:%M:%S'

COMPLIANCE_CHECKER_NORMAL_LIMIT = 2


@pytest.mark.usefixtures('default_metadata_type',
                         'indexed_ls5_scene_dataset_type')
def test_full_ingestion(global_integration_cli_args, index, example_ls5_dataset, ls5_nbar_ingest_config):
    opts = list(global_integration_cli_args)
    opts.extend(
        [
            '-vv',
            'index',
            '--match-rules',
            str(LS5_MATCH_RULES),
            str(example_ls5_dataset)
        ]
    )
    result = CliRunner().invoke(
        datacube.scripts.agdc.cli,
        opts,
        catch_exceptions=False
    )
    print(result.output)
    assert not result.exception
    assert result.exit_code == 0

    ensure_dataset_is_indexed(index)

    opts = list(global_integration_cli_args)
    opts.extend(
        [
            '-vv',
            'ingest',
            '--config',
            str(ls5_nbar_ingest_config)
        ]
    )
    result = CliRunner().invoke(
        datacube.scripts.agdc.cli,
        opts,
        catch_exceptions=False
    )
    print(result.output)
    assert not result.exception
    assert result.exit_code == 0

    datasets = index.datasets.search_eager(type='ls5_nbar_albers')
    assert len(datasets) > 0

    ds_path = str(datasets[0].local_path)
    with netCDF4.Dataset(ds_path) as nco:
        check_data_shape(nco)
        check_grid_mapping(nco)
        check_cf_compliance(nco)
        # TODO: check_dataset_metadata_in_storage_unit(nco, example_ls5_dataset)
        # TODO: check_global_attributes(nco, su.storage_type.global_attributes)
    check_open_with_xray(ds_path)
    # TODO: check_open_with_api(index)
    # TODO: can pull data out


def ensure_dataset_is_indexed(index):
    datasets = index.datasets.search_eager(metadata_type='eo')
    assert len(datasets) == 1
    assert datasets[0].id == EXAMPLE_LS5_DATASET_ID


def check_grid_mapping(nco):
    assert 'grid_mapping' in nco.variables['blue'].ncattrs()
    grid_mapping = nco.variables['blue'].grid_mapping
    assert grid_mapping in nco.variables
    assert 'GeoTransform' in nco.variables[grid_mapping].ncattrs()
    assert 'spatial_ref' in nco.variables[grid_mapping].ncattrs()


def check_data_shape(nco):
    assert nco.variables['blue'].shape == EXPECTED_STORAGE_UNIT_DATA_SHAPE


def check_cf_compliance(dataset):
    if not six.PY2:
        warnings.warn('compliance_checker non-functional in Python 3. Skipping NetCDF-CF Compliance Checks')
        return

    try:
        from compliance_checker.runner import CheckSuite, ComplianceChecker
    except ImportError:
        warnings.warn('compliance_checker unavailable, skipping NetCDF-CF Compliance Checks')
        return

    cs = CheckSuite()
    cs.load_all_available_checkers()
    score_groups = cs.run(dataset, 'cf')

    groups = ComplianceChecker.stdout_output(cs, score_groups, verbose=1, limit=COMPLIANCE_CHECKER_NORMAL_LIMIT)
    assert cs.passtree(groups, limit=COMPLIANCE_CHECKER_NORMAL_LIMIT)


def check_global_attributes(nco, attrs):
    for k, v in attrs.items():
        assert nco.getncattr(k) == v


def check_dataset_metadata_in_storage_unit(nco, dataset_dir):
    assert len(nco.variables['extra_metadata']) == 1  # 1 time slice
    stored_metadata = netCDF4.chartostring(nco.variables['extra_metadata'][0])
    stored_metadata = str(np.char.decode(stored_metadata))
    ds_filename = dataset_dir / 'agdc-metadata.yaml'
    with ds_filename.open() as f:
        orig_metadata = f.read()
    stored = make_pgsqljson_match_yaml_load(yaml.safe_load(stored_metadata))
    original = make_pgsqljson_match_yaml_load(yaml.safe_load(orig_metadata))
    assert stored == original


def check_open_with_xray(file_path):
    import xarray
    xarray.open_dataset(str(file_path))


def check_open_with_api(index):
    import datacube.api
    api = datacube.api.API(index=index)
    fields = api.list_fields()
    assert 'product' in fields
    descriptor = api.get_descriptor()
    assert 'ls5_nbar' in descriptor
    storage_units = descriptor['ls5_nbar']['storage_units']
    query = {
        'variables': ['blue'],
        'dimensions': {
            'latitude': {'range': (-34, -35)},
            'longitude': {'range': (149, 150)}}
    }
    data = api.get_data(query, storage_units=storage_units)
    assert abs(data['element_sizes'][1] - 0.025) < .0000001
    assert abs(data['element_sizes'][2] - 0.025) < .0000001

    data_array = api.get_data_array(storage_type='ls5_nbar', variables=['blue'],
                                    latitude=(-34, -35), longitude=(149, 150))
    assert data_array.size

    dataset = api.get_dataset(storage_type='ls5_nbar', variables=['blue'],
                              latitude=(-34, -35), longitude=(149, 150))
    assert dataset['blue'].size

    data_array_cell = api.get_data_array_by_cell((149, -34), storage_type='ls5_nbar', variables=['blue'])
    assert data_array_cell.size

    data_array_cell = api.get_data_array_by_cell(x_index=149, y_index=-34,
                                                 storage_type='ls5_nbar', variables=['blue'])
    assert data_array_cell.size

    dataset_cell = api.get_dataset_by_cell((149, -34), storage_type='ls5_nbar', variables=['blue'])
    assert dataset_cell['blue'].size

    dataset_cell = api.get_dataset_by_cell([(149, -34), (149, -35)], storage_type='ls5_nbar', variables=['blue'])
    assert dataset_cell['blue'].size

    dataset_cell = api.get_dataset_by_cell(x_index=149, y_index=-34, storage_type='ls5_nbar', variables=['blue'])
    assert dataset_cell['blue'].size

    tiles = api.list_tiles(x_index=149, y_index=-34, storage_type='ls5_nbar')
    for tile_query, tile_attrs in tiles:
        dataset = api.get_dataset_by_cell(**tile_query)
        assert dataset['blue'].size


def make_pgsqljson_match_yaml_load(data):
    """Un-munge YAML data passed through PostgreSQL JSON"""
    for key, value in data.items():
        if isinstance(value, dict):
            data[key] = make_pgsqljson_match_yaml_load(value)
        elif isinstance(value, datetime):
            data[key] = value.strftime(JSON_DATE_FORMAT)
        elif value is None:
            data[key] = {}
    return data
