#  Copyright (c) 2025 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

import json

import pytest

import bidslab as abk


@pytest.fixture(scope="class")
def json_sidecar(tmp_root):
    sidecar_path = tmp_root / "dataset_description.json"
    sidecar_content = {
        "Name": "Example Dataset",
        "BIDSVersion": "1.10.1",
        "License": "CC0",
        "Authors": ["Author One", "Author Two"],
        "Acknowledgements": "We thank everyone.",
        "HowToAcknowledge": "Please cite our paper.",
        "Funding": ["Grant A", "Grant B"],
        "EthicsApprovals": ["Approval 1", "Approval 2"],
        "ReferencesAndLinks": ["http://example.com"],
        "DatasetDOI": "10.1234/example.doi",
        "GeneratedBy": [
            {
                "Name": "Tool A",
                "Version": "1.0",
                "CodeURL": "http://toola.com",
            }
        ],
        "SourceDatasets": [
            {
                "URL": "http://sourcedataset.com",
                "DOI": "10.5678/source.doi",
            }
        ],
    }
    with sidecar_path.open("w") as f:
        json.dump(sidecar_content, f)
    return sidecar_path, sidecar_content


@pytest.fixture(scope="class")
def json_sidecar_schema(tmp_root):
    sidecar_path = tmp_root / "dataset_description.json"
    sidecar_content = {
        "Name": "Example Dataset",
        "BIDSVersion": "1.10.1",
        "License": "CC0",
        "Authors": ["Author One", "Author Two"],
        "Acknowledgements": "We thank everyone.",
        "HowToAcknowledge": "Please cite our paper.",
        "Funding": ["Grant A", "Grant B"],
        "EthicsApprovals": ["Approval 1", "Approval 2"],
        "ReferencesAndLinks": ["http://example.com"],
        "DatasetDOI": "10.1234/example.doi",
        "GeneratedBy": [
            {
                "Name": "Tool A",
                "Version": "1.0",
                "CodeURL": "http://toola.com",
            }
        ],
        "SourceDatasets": [
            {
                "URL": "http://sourcedataset.com",
                "DOI": "10.5678/source.doi",
            }
        ],
    }
    divided_dict = {
        "general": {
            "Name": "Example Dataset",
            "BIDSVersion": "1.10.1",
            "License": "CC0",
            "Authors": ["Author One", "Author Two"],
        },
        "rest": {
            "Acknowledgements": "We thank everyone.",
            "HowToAcknowledge": "Please cite our paper.",
            "Funding": ["Grant A", "Grant B"],
            "EthicsApprovals": ["Approval 1", "Approval 2"],
            "ReferencesAndLinks": ["http://example.com"],
            "DatasetDOI": "10.1234/example.doi",
            "GeneratedBy": [
                {
                    "Name": "Tool A",
                    "Version": "1.0",
                    "CodeURL": "http://toola.com",
                }
            ],
            "SourceDatasets": [
                {
                    "URL": "http://sourcedataset.com",
                    "DOI": "10.5678/source.doi",
                }
            ],
        },
    }
    with sidecar_path.open("w") as f:
        json.dump(sidecar_content, f)
    return sidecar_path, divided_dict


@pytest.fixture(scope="class")
def participants_tsv(tmp_root):
    tsv_path = tmp_root / "participants.tsv"
    tsv_content = "participant_id\tage\tsex\nsub-01\t29\tM\nsub-02\t34\tF\n"
    with tsv_path.open("w") as f:
        f.write(tsv_content)
    return tsv_path, [
        {"participant_id": "sub-01", "age": "29", "sex": "M"},
        {"participant_id": "sub-02", "age": "34", "sex": "F"},
    ]


class TestJSONParser:
    def test_parse_json_sidecar_valid(self, json_sidecar):
        parsed = abk.utils.helpers.parse_json_sidecar(json_sidecar[0])

        assert parsed == json_sidecar[1]

    def test_parse_json_sidecar_schema(self, json_sidecar_schema):
        parsed = abk.utils.helpers.parse_json_sidecar(
            json_sidecar_schema[0],
            {"general": {"Name", "BIDSVersion", "License", "Authors"}},
        )

        assert parsed == json_sidecar_schema[1]


class TestTSVParser:
    def test_parse_descriptive_tsv_valid(self, participants_tsv):
        parsed = list(abk.utils.helpers.parse_descriptive_tsv(participants_tsv[0]))

        assert parsed == participants_tsv[1]
