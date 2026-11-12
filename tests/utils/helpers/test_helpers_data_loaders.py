#  Copyright (c) 2026 by Lukas Behammer, Tobias Noak
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

import pathlib

import datalad as dl
import numpy as np
import pandas as pd
import pytest
from mimesis.enums import (
    FileType,
)

import bidslab as abk
from tests.conftest import (
    delete_files,
    make_files,
)

SYSTEMS = ["linux", "darwin", "win64"]
PATH_TYPES = ["pathlib", "str"]
FILE_TYPES = list(FileType)


@pytest.fixture
def sample_data_tsv():
    return [["test", "non", "numeric", "data"], [0, 1, 2, 3], [0.1, 0.2, 0.3, 0.4]]


@pytest.fixture
def sample_data_numeric_tsv():
    return [[10, 20, 30, 40], [0, 1, 2, 3], [0.1, 0.2, 0.3, 0.4]]


class TestGetDataDecorator:
    def test_no_path_argument(self):
        # Setup
        @abk.utils.helpers.get_data()
        def to_be_decorated(*, path: pathlib.Path):
            return 1

        # Test
        with pytest.raises(abk.utils.exceptions.MisusedDecoratorError):
            to_be_decorated()

    def test_invalid_path_argument(self):
        # Setup
        @abk.utils.helpers.get_data()
        def to_be_decorated(*, path: pathlib.Path):
            return 1

        # Test
        with pytest.raises(abk.utils.exceptions.MisusedDecoratorError):
            to_be_decorated(path=1)

    def test_no_fetching_package(self, tmp_root):
        # Setup
        @abk.utils.helpers.get_data()
        def to_be_decorated(*, path: pathlib.Path):
            return 1

        # Test
        with pytest.raises(ValueError):
            to_be_decorated(path=tmp_root / "test.tsv")

    def test_existing_path_no_errors(self, tmp_root):
        # Setup
        retrun_value = None
        files = ["test.tsv"]
        make_files(tmp_root, files)

        @abk.utils.helpers.get_data()
        def to_be_decorated(*, path: pathlib.Path):
            return 1

        # Test
        retrun_value = to_be_decorated(path=(tmp_root / files[0]))
        assert retrun_value == 1

        # Teardown
        delete_files(tmp_root, files)

    def test_data_fetching_package_datalad(self, tmp_root, monkeypatch):
        # Setup
        retrun_value = None

        @abk.utils.helpers.get_data()
        def to_be_decorated(*, path: pathlib.Path):
            return 1

        monkeypatch.setattr(dl.api, "get", lambda path: None)

        # Test
        with abk.settings.override_settings_values(
            {"DATASET_FETCHING_PACKAGE": abk.settings.PackageFetching.DATALAD}
        ):
            retrun_value = to_be_decorated(path=(tmp_root / "test.tsv"))

        assert retrun_value == 1

    def test_data_fetching_package_unknown(self, tmp_root):
        # Setup
        retrun_value = None

        @abk.utils.helpers.get_data()
        def to_be_decorated(*, path: pathlib.Path):
            return 1

        # Test
        with pytest.raises(ValueError):
            with abk.settings.override_settings_values(
                {"DATASET_FETCHING_PACKAGE": "some_package"}
            ):
                retrun_value = to_be_decorated(path=tmp_root / "test.tsv")
        assert retrun_value is None


class TestLoadTSVData:
    def test_load_tsv_numeric_numpy(self, tmp_root, sample_data_numeric_tsv):
        # Setup
        expected_data = sample_data_numeric_tsv
        dataframe = pd.DataFrame(expected_data)
        dataframe.to_csv(
            tmp_root / "test.tsv",
            sep="\t",
            index=False,
            header=False,
        )

        # Test
        with abk.settings.override_settings_values(
            {"DATA_LOADING_PACKAGE": abk.settings.PackageLoading.NUMPY}
        ):
            loaded_data = abk.utils.helpers.load_tsv_data(path=(tmp_root / "test.tsv"))
        assert (loaded_data == np.array(expected_data)).all()

        # Teardown
        delete_files(tmp_root, ["test.tsv"])

    def test_load_tsv_non_numeric_numpy(self, tmp_root, sample_data_tsv):
        # Setup
        expected_data = sample_data_tsv
        dataframe = pd.DataFrame(expected_data)
        dataframe.to_csv(
            tmp_root / "test.tsv",
            sep="\t",
            index=False,
            header=False,
        )

        # Test
        with pytest.raises(ValueError):
            with abk.settings.override_settings_values(
                {"DATA_LOADING_PACKAGE": abk.settings.PackageLoading.NUMPY}
            ):
                abk.utils.helpers.load_tsv_data(path=(tmp_root / "test.tsv"))

        # Teardown
        delete_files(tmp_root, ["test.tsv"])

    def test_load_tsv_pandas(self, tmp_root, sample_data_tsv):
        # Setup
        expected_data = sample_data_tsv
        dataframe = pd.DataFrame(expected_data)
        dataframe.to_csv(
            tmp_root / "test.tsv",
            sep="\t",
            index=False,
            header=False,
        )

        # Test
        with abk.settings.override_settings_values(
            {"DATA_LOADING_PACKAGE": abk.settings.PackageLoading.PANDAS}
        ):
            loaded_data = abk.utils.helpers.load_tsv_data(path=(tmp_root / "test.tsv"))
        pd.testing.assert_frame_equal(loaded_data.astype(str), dataframe.astype(str))

        # Teardown
        delete_files(tmp_root, ["test.tsv"])

    def test_load_tsv_gz_numpy(self, tmp_root, sample_data_numeric_tsv):
        # Setup
        expected_data = sample_data_numeric_tsv
        dataframe = pd.DataFrame(expected_data)
        dataframe.to_csv(
            tmp_root / "test.tsv.gz",
            sep="\t",
            index=False,
            header=False,
            compression="gzip",
        )

        # Test
        with abk.settings.override_settings_values(
            {"DATA_LOADING_PACKAGE": abk.settings.PackageLoading.NUMPY}
        ):
            loaded_data = abk.utils.helpers.load_tsv_data(
                path=(tmp_root / "test.tsv.gz")
            )
        assert (loaded_data == np.array(expected_data)).all()

        # Teardown
        delete_files(tmp_root, ["test.tsv.gz"])

    def test_load_tsv_gz_pandas(self, tmp_root, sample_data_tsv):
        # Setup
        expected_data = sample_data_tsv
        dataframe = pd.DataFrame(expected_data)
        dataframe.to_csv(
            tmp_root / "test.tsv.gz",
            sep="\t",
            index=False,
            header=False,
            compression="gzip",
        )
        # Test
        with abk.settings.override_settings_values(
            {"DATA_LOADING_PACKAGE": abk.settings.PackageLoading.PANDAS}
        ):
            loaded_data = abk.utils.helpers.load_tsv_data(
                path=(tmp_root / "test.tsv.gz")
            )
        pd.testing.assert_frame_equal(loaded_data.astype(str), dataframe.astype(str))

        # Teardown
        delete_files(tmp_root, ["test.tsv.gz"])

    def test_load_tsv_data_load_package_unknown(self, tmp_root):
        # Setup
        files = ["test.tsv"]
        make_files(tmp_root, files)

        # Test
        with pytest.raises(ValueError):
            with abk.settings.override_settings_values(
                {"DATA_LOADING_PACKAGE": "some_pacage"}
            ):
                abk.utils.helpers.load_tsv_data(path=(tmp_root / "test.tsv"))

        # Teardown
        delete_files(tmp_root, ["test.tsv"])


# TODO
class TestLoadEDFData:
    def test_load_edf(self):
        pass

    def test_load_edf_plus(self):
        pass
