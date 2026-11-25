#  Copyright (c) 2025 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

import pathlib
import sys

import pytest

import bidslab as abk


@pytest.fixture
def cleaned_sample_dict():
    return {
        "level1": {
            "level2": {
                "key1": "value1",
                "path_key": "/some/path",
            },
            "path_key2": "/some/other/path",
            "Levels": {"some_level": {"Description": "some description"}},
        },
        "list_with_none": [
            {"subkey1": "subvalue1"},
            "a_string",
        ],
        "another_key": "another_value",
    }


@pytest.fixture
def levels_sample_dict():
    return {
        "level1": {
            "level2": {
                "key1": "value1",
                "path_key": "/some/path",
            },
            "path_key2": "/some/other/path",
            "Levels": {"test": {"Description": "test description"}},
        },
        "list_with_none": [
            {"subkey1": "subvalue1"},
            "a_string",
        ],
        "another_key": "another_value",
    }


@pytest.fixture
def sample_dict():
    return {
        "level1": {
            "level2": {
                "key1": "value1",
                "key2": None,
                "_private_key": "private_value",
                "path_key": pathlib.Path("/some/path"),
            },
            "path_key2": pathlib.Path("/some/other/path"),
            "Levels": {"some_level": {"Description": "some description"}},
        },
        "list_with_none": [
            {"subkey1": "subvalue1", "subkey2": None},
            "a_string",
        ],
        "another_key": "another_value",
        "_private_key2": "private_value2",
        "root": pathlib.Path("/a/root/path"),
    }


class TestAddLevelsToDict:
    def test_add_levels_to_dict(self, cleaned_sample_dict, levels_sample_dict):
        levels_dict = cleaned_sample_dict
        abk.utils.dict_manipulation.add_levels_to_dict(
            [
                abk.common.specs_misc.Level(
                    level_name="test", description="test description"
                )
            ],
            "level1",
            levels_dict,
        )

        assert levels_dict == levels_sample_dict


class TestCleanDict:
    # Will raise DeprecationWarning in Python versions < 3.12
    @pytest.mark.xfail(
        sys.version_info < (3, 12),
        reason="requires python3.12",
        raises=(TypeError, DeprecationWarning),
    )
    def test_clean_dict_titlecase(self, sample_dict, cleaned_sample_dict):
        cleaned_dict = abk.utils.dict_manipulation.clean_dict(
            sample_dict, skip_keys_to_manipulate=0
        )

        assert cleaned_dict == abk.utils.dict_manipulation.manipulate_dictkeys(
            cleaned_sample_dict
        )

    # Will raise DeprecationWarning in Python versions < 3.12
    @pytest.mark.xfail(
        sys.version_info < (3, 12),
        reason="requires python3.12",
        raises=(TypeError, DeprecationWarning),
    )
    def test_clean_dict_no_titlecase(self, sample_dict, cleaned_sample_dict):
        cleaned_dict = abk.utils.dict_manipulation.clean_dict(
            sample_dict, skip_keys_to_manipulate=-1
        )

        assert cleaned_dict == cleaned_sample_dict


class TestDeleteNoneFromDict:
    def test_delete_none_from_dict(self, sample_dict):
        cleaned_dict = abk.utils.dict_manipulation.delete_none_from_dict(sample_dict)

        assert "key2" not in cleaned_dict["level1"]["level2"]
        assert "subkey2" not in cleaned_dict["list_with_none"][1]


class TestDeletePrivateFieldsFromDict:
    def test_delete_private_fields_from_dict(self, sample_dict):
        cleaned_dict = abk.utils.dict_manipulation.delete_private_fields_from_dict(
            sample_dict
        )

        assert "_private_key" not in cleaned_dict["level1"]["level2"]
        assert "_private_key2" not in cleaned_dict


class TestDictKeysToTitlecase:
    def test_dict_keys_to_titlecase(self, sample_dict):
        titled_dict = abk.utils.dict_manipulation.manipulate_dictkeys(sample_dict)

        assert "Level1" in titled_dict
        assert "Level2" in titled_dict["Level1"]
        assert "Key1" in titled_dict["Level1"]["Level2"]
        assert "AnotherKey" in titled_dict


class TestDictPathsToStrings:
    def test_dict_paths_to_strings(self, sample_dict):
        stringified_dict = abk.utils.dict_manipulation.dict_paths_to_strings(
            sample_dict
        )

        assert isinstance(stringified_dict["level1"]["level2"]["path_key"], str)
        assert isinstance(stringified_dict["level1"]["path_key2"], str)
