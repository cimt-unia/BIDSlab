#  Copyright (c) 2025 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

import pathlib
from warnings import warn

import pytest
from mimesis import BinaryFile, File, Path, Text
from mimesis.enums import (
    AudioFile,
    CompressedFile,
    DocumentFile,
    FileType,
    ImageFile,
    VideoFile,
)
from mimesis.random import Random

import bidslab as abk
from bidslab.utils.exceptions import FieldNotValidError, TopLevelEntityNotLinkedWarning
from tests.conftest import FixtureParameterNotSupportedError, _permutate_dict

SYSTEMS = ["linux", "darwin", "win64"]
PATH_TYPES = ["pathlib", "str"]
FILE_TYPES = list(FileType)


@pytest.fixture(params=FILE_TYPES)
def create_binary_test_file(tmp_root, request):
    file_name = File().file_name(request.param)
    if request.param.value == "audio":
        binary_data = BinaryFile().audio(file_type=Random().choice_enum_item(AudioFile))
    elif request.param.value == "video":
        binary_data = BinaryFile().video(file_type=Random().choice_enum_item(VideoFile))
    elif request.param.value == "image":
        binary_data = BinaryFile().image(file_type=Random().choice_enum_item(ImageFile))
    elif request.param.value == "text":
        binary_data = BinaryFile().document(
            file_type=Random().choice_enum_item(DocumentFile)
        )
    elif request.param.value == "compressed":
        binary_data = BinaryFile().compressed(
            file_type=Random().choice_enum_item(CompressedFile)
        )
    elif request.param.value in ["executable", "data", "source"]:
        pytest.skip("Binary file type not supported by mimesis.")
    else:
        raise FixtureParameterNotSupportedError("Test parameter not supported.")
    source = tmp_root / file_name
    source.touch()
    source.write_bytes(binary_data)
    destination = tmp_root / ("dest_" + file_name)
    return source, destination, binary_data


@pytest.fixture
def sample_path(request):
    if request.param["path_type"] == "str":
        return Path(request.param["system"]).project_dir()
    if request.param["path_type"] == "pathlib":
        return pathlib.Path(Path(request.param["system"]).project_dir())
    raise FixtureParameterNotSupportedError("Test parameter not supported.")


class SampleClass:
    def __init__(self, attr1=None, attr2=None):
        self.attr1 = attr1
        self.attr2 = attr2


class SampleClassWarnTopLevel:
    def __init__(self, attr1=None):
        self.attr1 = attr1

        warn("Top level entity not linked", TopLevelEntityNotLinkedWarning)


class TestSetClassAttributes:
    def test_set_class_attributes_from_dict(self):
        # Setup
        attr_dict = {"attr1": "value1", "attr2": 42}
        sample = SampleClass()

        # Test
        abk.utils.helpers.set_attr_from_dict(sample, attr_dict)

        assert sample.attr1 == "value1"
        assert sample.attr2 == 42

    def test_set_class_attributes_with_invalid_key(self):
        # Setup
        attr_dict = {"attr1": "value1", "attr3": "value3"}
        sample = SampleClass()

        # Test
        assert not hasattr(sample, "attr3")
        with pytest.raises(FieldNotValidError):
            abk.utils.helpers.set_attr_from_dict(sample, attr_dict)

        assert not hasattr(sample, "attr3")

    def test_set_class_attributes_missing_top_level_entity(self):
        # Setup
        attr_dict = {"attr1": "value1"}
        with pytest.warns(TopLevelEntityNotLinkedWarning):
            sample = SampleClassWarnTopLevel()

        # Test
        abk.utils.helpers.set_attr_from_dict(sample, attr_dict)  # No warning here
        assert sample.attr1 == "value1"


class TestAddObjectToSequence:
    def test_add_object_to_sequence(self):
        # Setup
        entity_list = []
        entity = SampleClass

        # Test
        abk.utils.helpers.add_object_to_sequence(entity_list, entity)
        assert type(entity_list[0]) is SampleClass

    def test_add_object_to_sequence_with_nonempty_list(self):
        # Setup
        entity_list = [SampleClass()]
        entity = SampleClass

        # Test
        abk.utils.helpers.add_object_to_sequence(entity_list, entity)
        assert type(entity_list[1]) is SampleClass
        assert len(entity_list) == 2

    def test_add_object_to_sequence_multiple_times(self):
        # Setup
        entity_list = []
        entity = SampleClass

        # Test
        abk.utils.helpers.add_object_to_sequence(entity_list, entity)
        abk.utils.helpers.add_object_to_sequence(entity_list, entity)
        assert type(entity_list[0]) is SampleClass
        assert type(entity_list[1]) is SampleClass
        assert len(entity_list) == 2

    def test_add_object_to_sequence_with_arguments(self):
        # Setup
        entity_list = []
        entity = SampleClass
        args = {"attr1": "value1"}

        # Test
        abk.utils.helpers.add_object_to_sequence(entity_list, entity, **args)
        assert type(entity_list[0]) is SampleClass
        assert entity_list[0].attr1 == "value1"

    def test_add_object_to_sequence_with_invalid_entity(self):
        # Setup
        entity_list = []
        entity = "NotAClass"

        # Test
        with pytest.raises(TypeError):
            abk.utils.helpers.add_object_to_sequence(entity_list, entity)
        assert len(entity_list) == 0


class TestAppendPath:
    @pytest.mark.parametrize(
        "sample_path",
        _permutate_dict({"system": SYSTEMS, "path_type": PATH_TYPES}),
        indirect=True,
    )
    def test_append_path(self, sample_path):
        # Setup
        appendix = "_" + Text().word()

        # Test
        long_path = abk.utils.helpers.append_path(sample_path, appendix)
        assert isinstance(long_path, pathlib.Path)
        assert str(long_path) == str(sample_path) + appendix


class TestCopyFile:
    def test_copy_file(self, create_binary_test_file):
        # Setup
        source, destination, binary_data = create_binary_test_file

        # Test
        assert not destination.exists()
        abk.utils.helpers.copy_file(source, destination)
        assert destination.exists()
        assert destination.read_bytes() == binary_data

        # Teardown
        source.unlink()
        destination.unlink()

    def test_copy_file_no_existing_source(self, create_binary_test_file):
        # Setup
        source, destination, _binary_data = create_binary_test_file
        source.unlink()

        # Test
        assert not destination.exists()
        assert not source.exists()
        with pytest.raises(FileNotFoundError):
            abk.utils.helpers.copy_file(source, destination)
        assert not destination.exists()

    def test_copy_file_same_source_destination(self, tmp_root):
        # Setup
        source = tmp_root / "testfile.txt"
        destination = tmp_root / "testfile.txt"

        # Test
        with pytest.warns(abk.utils.helpers.PathsSameWarning):
            abk.utils.helpers.copy_file(source, destination)
        assert not destination.exists()


class TestWriteEntities:
    # TODO: Implement tests
    def test_write_entities_one_required(self):
        pass

    def test_write_entities_multiple_required(self):
        pass

    def test_write_entities_one_optional(self):
        pass

    def test_write_entities_multiple_optional(self):
        pass

    def test_write_entities_no_entity(self):
        pass
