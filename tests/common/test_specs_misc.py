#  Copyright (c) 2026 by Lukas Behammer, Tobias Noak
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

import json

import numpy as np
import pandas as pd
import pytest
from mimesis.enums import FileType

import bidslab as abk
from tests.conftest import (
    delete_files,
    make_files,
)

SYSTEMS = ["linux", "darwin", "win64"]
PATH_TYPES = ["pathlib", "str"]
FILE_TYPES = list(FileType)


@pytest.fixture
def generate_events_json(tmp_root):
    def _generate(
        filename="test_events.json",
        **overrides,
    ):
        data = {
            "trial_type": {
                "LongName": "Event category",
                "Description": "Indicator of type of action that is expected",
                "Levels": {
                    "start": "A red square is displayed to indicate starting",
                    "stop": "A blue square is displayed to indicate stopping",
                },
            },
            "channel": {
                "Description": "Channel(s) associated with the event",
                "Delimiter": "|",
            },
            "annots": {
                "LongName": "Annotations",
                "Description": "Annotations associated with channels indicated...",
                "Levels": {"musc": "Muscle artifact. A very common, high frequency..."},
                "HED": {"musc": "EMG-artifact"},
            },
        }

        data.update(overrides)

        output_path = tmp_root / filename
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=4,
                ensure_ascii=False,
            )

        return output_path

    return _generate


@pytest.fixture
def generate_events_tsv(tmp_root):
    def _generate(
        filename="test_events.tsv",
    ):
        data = pd.DataFrame(
            [
                [1.23, 0.65, "start", "1.435", "images/red_square.jpg", "n/a", "n/a"],
                [12.1, 2.35, "n/a", "n/a", "n/a", "F,1|F,2|Cz", "musc"],
            ],
            columns=[
                "onset",
                "duration",
                "trial_type",
                "response_time",
                "stim_file",
                "channel",
                "annots",
            ],
        )

        output_path = tmp_root / filename
        data.to_csv(output_path, sep="\t", index=False, header=True)
        return output_path

    return _generate


@pytest.fixture
def generate_physio_json(tmp_root):
    def _generate(
        filename="test_physio.json",
        **overrides,
    ):
        data = {
            "Columns": ["cardiac", "respiratory", "trigger"],
            "Manufacturer": "Brain Research Equipment ltd.",
            "PhysioType": "generic",
            "SamplingFrequency": 100.0,
            "StartTime": -22.345,
            "cardiac": {"Description": "continuous pulse measurement", "Units": "mV"},
            "respiratory": {
                "Description": "continuous measurements by respiration belt",
                "Units": "mV",
            },
            "trigger": {
                "Description": "continuous measurement of the scanner trigger signal",
                "Units": "V",
            },
        }

        data.update(overrides)

        output_path = tmp_root / filename
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=4,
                ensure_ascii=False,
            )

        return output_path

    return _generate


@pytest.fixture
def generate_stims_json(tmp_root):
    def _generate(
        filename="test_stim.json",
        **overrides,
    ):
        data = {
            "Columns": ["column 1", "column 2"],
            "SamplingFrequency": 100.0,
            "StartTime": -22.345,
        }

        data.update(overrides)

        output_path = tmp_root / filename
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=4,
                ensure_ascii=False,
            )

        return output_path

    return _generate


class TestPhysioRecording:
    def test_attribute_setting(self, tmp_root):
        # Setup
        args = {
            "base_path": tmp_root,
            "recording_id": "recording-1",
            "sampling_frequency": 10,
            "start_time": 0.05,
            "columns": [abk.common.specs_misc.Column("some_column_name")],
            "physio_type": "some physio type",
        }

        # Test
        physio = abk.common.specs_misc.PhysioRecording(
            *args.values(),
            virtual_entity=True,
            some_other_argument="some other value",
        )
        assert physio.root == tmp_root
        assert physio.recording_id == "recording-1"
        assert physio.sampling_frequency == 10
        assert np.isclose(physio.start_time, 0.05, rtol=1e-9, atol=1e-9)
        assert physio.physio_type == "some physio type"
        assert physio.some_other_argument == "some other value"
        assert physio.columns[0].column_name == "some_column_name"
        assert physio._virtual_entity is True

    def test_data(self, tmp_root, monkeypatch):
        # Setup
        def mock_get_top_level_entities(self):
            return [self._entity_id]

        monkeypatch.setattr(
            abk.common.specs_misc.PhysioRecording,
            "get_top_level_entities",
            mock_get_top_level_entities,
        )

        physio = abk.common.specs_misc.PhysioRecording(
            tmp_root,
            "recording-0",
            1,
            0,
            [abk.common.specs_misc.Column("some_column_name")],
        )
        expected_data = pd.DataFrame([[0, 1, 2], [0.2, 0.3, 0.4]])
        expected_data.to_csv(
            tmp_root / "recording-0_physio.tsv.gz",
            sep="\t",
            index=False,
            header=False,
            compression="gzip",
        )

        # Test
        data = physio.data
        assert (np.array(data) == np.array(expected_data)).all()

        # Teardown
        delete_files(tmp_root, ["recording-0_physio.tsv.gz"])

    # TODO write test for write function
    def test_write(self):
        pass


class TestStimRecording:
    def test_attribute_setting(self, tmp_root):
        # Setup
        args = {
            "base_path": tmp_root,
            "recording_id": "recording-1",
            "sampling_frequency": 10,
            "start_time": 0.05,
            "columns": [abk.common.specs_misc.Column("some_column_name")],
        }

        # Test
        stims = abk.common.specs_misc.StimRecording(
            *args.values(),
            virtual_entity=True,
            some_other_argument="some other value",
        )
        assert stims.root == tmp_root
        assert stims.recording_id == "recording-1"
        assert stims.sampling_frequency == 10
        assert np.isclose(stims.start_time, 0.05, rtol=1e-9, atol=1e-9)
        assert stims.some_other_argument == "some other value"
        assert stims.columns[0].column_name == "some_column_name"
        assert stims._virtual_entity is True

    def test_data(self, tmp_root, monkeypatch):
        # Setup
        def mock_get_top_level_entities(self):
            return [self._entity_id]

        monkeypatch.setattr(
            abk.common.specs_misc.StimRecording,
            "get_top_level_entities",
            mock_get_top_level_entities,
        )

        stim = abk.common.specs_misc.StimRecording(
            tmp_root / "sub-1/eeg",
            "recording-0",
            1,
            0,
            [abk.common.specs_misc.Column("some_column_name")],
        )
        expected_data = pd.DataFrame([[0, 1, 2], [0.2, 0.3, 0.4]])
        make_files(tmp_root, ["sub-1/eeg/recording-0_stim.tsv.gz"])
        expected_data.to_csv(
            tmp_root / "sub-1/eeg/recording-0_stim.tsv.gz",
            sep="\t",
            index=False,
            header=False,
            compression="gzip",
        )

        # Test
        data = stim.data
        assert (np.array(data) == np.array(expected_data)).all()

        # Teardown
        delete_files(tmp_root, ["sub-1/eeg/recording-0_stim.tsv.gz"])

    # TODO write test for write function
    def test_write(self):
        pass


class TestGetEvents:
    def test_bad_directory_structure(self, tmp_root, monkeypatch):
        # Setup
        files = [
            "sub-0/something_wrong/anat/run-0_events.tsv",
            "sub-0/something_wrong/anat/run-0_events.json",
        ]
        make_files(tmp_root, files)

        def mock_get_top_level_entities(self):
            return [self._entity_id]

        monkeypatch.setattr(
            abk.common.specs_misc.Run,
            "get_top_level_entities",
            mock_get_top_level_entities,
        )

        run = abk.common.specs_misc.Run(tmp_root, 0)

        # Test
        with pytest.raises(abk.utils.exceptions.BadDirectoryStructureError):
            abk.common.specs_misc.get_events_from_files(
                run, tmp_root / "sub-0/something_wrong/anat"
            )

        # Teardown
        delete_files(tmp_root, files)

    def test_no_files(self, tmp_root, monkeypatch):
        # Setup
        files = [
            "sub-0/ses-0/anat/run-2_events.tsv",
            "sub-0/ses-0/anat/run-2_events.json",
        ]
        make_files(tmp_root, files)

        def mock_get_top_level_entities(self):
            return [self._entity_id]

        monkeypatch.setattr(
            abk.common.specs_misc.Run,
            "get_top_level_entities",
            mock_get_top_level_entities,
        )

        run = abk.common.specs_misc.Run(tmp_root, 0)

        # Test
        events = abk.common.specs_misc.get_events_from_files(
            run, tmp_root / "sub-0/ses-0/anat"
        )
        assert events == []

        # Teardown
        delete_files(tmp_root, files)

    def test_no_json(self, tmp_root, monkeypatch, generate_events_tsv):
        # Setup
        files = [
            "sub-0/ses-0/anat/run-0_events.tsv",
        ]

        make_files(tmp_root, files)
        generate_events_tsv(filename="sub-0/ses-0/anat/run-0_events.tsv")

        def mock_get_top_level_entities(self):
            return [self._entity_id]

        monkeypatch.setattr(
            abk.common.specs_misc.Run,
            "get_top_level_entities",
            mock_get_top_level_entities,
        )

        run = abk.common.specs_misc.Run(tmp_root, 0)

        # Test
        events = abk.common.specs_misc.get_events_from_files(
            run, tmp_root / "sub-0/ses-0/anat"
        )
        assert len(events) == 2
        assert np.isclose(events[0].onset, 1.23, rtol=1e-9, atol=1e-9)
        assert events[0].annots == "n/a"
        assert np.isclose(events[1].onset, 12.1, rtol=1e-9, atol=1e-9)
        assert events[1].annots == "musc"

        # Teardown
        delete_files(tmp_root, files)

    def test_no_tsv(self, tmp_root, monkeypatch, generate_events_json):
        # Setup
        files = [
            "sub-0/ses-0/anat/run-0_events.json",
        ]

        make_files(tmp_root, files)
        generate_events_json(filename="sub-0/ses-0/anat/run-0_events.json")

        def mock_get_top_level_entities(self):
            return [self._entity_id]

        monkeypatch.setattr(
            abk.common.specs_misc.Run,
            "get_top_level_entities",
            mock_get_top_level_entities,
        )

        run = abk.common.specs_misc.Run(tmp_root, 0)

        # Test
        with pytest.warns(
            UserWarning, match=r"JSON file found, but no suitable TSV file available"
        ):
            events = abk.common.specs_misc.get_events_from_files(
                run, tmp_root / "sub-0/ses-0/anat"
            )
        assert events == []

        # Teardown
        delete_files(tmp_root, files)

    def test_files_in_higher_directory(
        self, tmp_root, monkeypatch, generate_events_json, generate_events_tsv
    ):
        # Setup
        files = [
            "sub-0/ses-0/anat/some_other_file.tsv",
            "sub-0/ses-0/run-0_events.tsv",
            "sub-0/run-0_events.json",
        ]
        make_files(tmp_root, files)
        generate_events_json(filename="sub-0/run-0_events.json")
        generate_events_tsv(filename="sub-0/ses-0/run-0_events.tsv")

        def mock_get_top_level_entities(self):
            return [self._entity_id]

        monkeypatch.setattr(
            abk.common.specs_misc.Run,
            "get_top_level_entities",
            mock_get_top_level_entities,
        )

        run = abk.common.specs_misc.Run(tmp_root, 0)

        # Test
        events = abk.common.specs_misc.get_events_from_files(
            run, tmp_root / "sub-0/ses-0/anat"
        )
        assert len(events) == 2
        assert np.isclose(events[0].onset, 1.23, rtol=1e-9, atol=1e-9)
        assert events[0].annots == "n/a"
        assert np.isclose(events[1].onset, 12.1, rtol=1e-9, atol=1e-9)
        assert events[1].annots == "musc"

        # Teardown
        delete_files(tmp_root, files)


class TestWriteEvents:
    # test write events
    def test_write_events(self, tmp_root, monkeypatch):
        # Setup
        make_files(
            tmp_root,
            ["ds2/stimuli/some_file.bmp", "ds1/sub-0/ses-0/anat/run-2_events.tsv"],
        )
        columns = {
            "trial_type": {
                "LongName": "Event category",
                "Description": "Indicator of type of action that is expected",
                "Levels": {
                    "start": "A red square is displayed to indicate starting",
                    "stop": "A blue square is displayed to indicate stopping",
                },
            },
            "channel": {
                "Description": "Channel(s) associated with the event",
                "Delimiter": "|",
            },
        }

        def mock_get_top_level_entities(self):
            return [self._entity_id]

        monkeypatch.setattr(
            abk.common.specs_misc.Run,
            "get_top_level_entities",
            mock_get_top_level_entities,
        )

        run = abk.common.specs_misc.Run(tmp_root / "ds2/sub-0/ses-0/anat", 0)
        events = [
            abk.common.specs_misc.Event(
                onset=0, duration=1, stim_file="some_file.bmp", columns=columns
            ),
            abk.common.specs_misc.Event(
                onset=1, duration=2, stim_file="n/a", columns=columns
            ),
        ]

        # Test
        abk.common.specs_misc.write_events_to_files(
            run, events, tmp_root / "ds1/sub-0/ses-0/anat/run-0"
        )

        assert (tmp_root / "ds1/sub-0/ses-0/anat/run-0_events.tsv").exists()
        assert (tmp_root / "ds1/sub-0/ses-0/anat/run-0_events.json").exists()
        assert (tmp_root / "ds1/stimuli/some_file.bmp").exists()

        # Teardown
        files = [
            "ds1/sub-0/ses-0/anat/run-0_events.tsv",
            "ds1/sub-0/ses-0/anat/run-0_events.json",
            "ds1/stimuli/some_file.bmp",
            "ds2/stimuli/some_file.bmp",
            "ds1/sub-0/ses-0/anat/run-2_events.tsv",
        ]
        delete_files(tmp_root, files)

    # test write physioevents (.tsv.gz)
    def test_write_physioevents(self, tmp_root, monkeypatch):  # Setup
        columns = {
            "trial_type": {
                "LongName": "Event category",
                "Description": "Indicator of type of action that is expected",
                "Levels": {
                    "start": "A red square is displayed to indicate starting",
                    "stop": "A blue square is displayed to indicate stopping",
                },
            },
            "channel": {
                "Description": "Channel(s) associated with the event",
                "Delimiter": "|",
            },
        }

        def mock_get_top_level_entities(self):
            return [self._entity_id]

        monkeypatch.setattr(
            abk.common.specs_misc.Run,
            "get_top_level_entities",
            mock_get_top_level_entities,
        )

        run = abk.common.specs_misc.Run(tmp_root, 0)
        events = [
            abk.common.specs_misc.Event(onset=0, duration=1, columns=columns),
            abk.common.specs_misc.Event(onset=1, duration=2, columns=columns),
        ]

        # Test
        abk.common.specs_misc.write_events_to_files(
            run,
            events,
            tmp_root / "run-0",
            file_ending="physioevents",
            compressed=True,
        )

        assert (tmp_root / "run-0_physioevents.tsv.gz").exists()
        assert (tmp_root / "run-0_physioevents.json").exists()

        # Teardown
        delete_files(tmp_root, ["run-0_physioevents.tsv.gz", "run-0_physioevents.json"])

    # test writing stimuli if directories dont follow the expected scheme
    def test_write_events_bad_directory_structure(self, tmp_root, monkeypatch):
        # Setup
        columns = {
            "trial_type": {
                "LongName": "Event category",
                "Description": "Indicator of type of action that is expected",
                "Levels": {
                    "start": "A red square is displayed to indicate starting",
                    "stop": "A blue square is displayed to indicate stopping",
                },
            },
            "channel": {
                "Description": "Channel(s) associated with the event",
                "Delimiter": "|",
            },
        }

        def mock_get_top_level_entities(self):
            return [self._entity_id]

        monkeypatch.setattr(
            abk.common.specs_misc.Run,
            "get_top_level_entities",
            mock_get_top_level_entities,
        )

        run = abk.common.specs_misc.Run(tmp_root, 0)
        events = [
            abk.common.specs_misc.Event(
                onset=0, duration=1, stim_file="some_file.bmp", columns=columns
            ),
            abk.common.specs_misc.Event(
                onset=1, duration=2, stim_file="n/a", columns=columns
            ),
        ]

        # Test
        with pytest.raises(abk.utils.exceptions.BadDirectoryStructureError):
            abk.common.specs_misc.write_events_to_files(run, events, tmp_root / "run-0")

        # Teardown
        delete_files(tmp_root, ["run-0_events.tsv", "run-0_events.json"])
