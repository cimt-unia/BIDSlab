# BIDSlab – *B*rain *I*maging *D*ata *S*tructure *lab*oratory <!-- codespell:ignore tructure -->

[![Project Status: Active – The project has reached a stable, usable state and is being actively developed.](https://www.repostatus.org/badges/latest/active.svg)](https://www.repostatus.org/#active)

[![PyPI - Version](https://img.shields.io/pypi/v/bidslab)](https://pypi.org/project/bidslab/bidslab)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/bidslab)](https://pypi.org/project/bidslab/)
[![PyPI - License](https://img.shields.io/pypi/l/bidslab)](https://pypi.org/project/bidslab/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/bidslab)](https://pypi.org/project/bidslab/)

[![codecov](https://codecov.io/github/cimt-unia/BIDSlab/graph/badge.svg)](https://codecov.io/github/cimt-unia/BIDSlab)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.0-4baaaa.svg)](https://github.com/cimt-unia/pyTermite/blob/main/CODE_OF_CONDUCT.md)

[![readthedocs](https://app.readthedocs.org/projects/bidslab/badge/?version=latest)](https://bidslab.readthedocs.io/en/latest/index.html)
[![CI](https://github.com/cimt-unia/bidslab/actions/workflows/ci.yml/badge.svg)](https://github.com/cimt-unia/bidslab/actions/workflows/ci.yml)
[![Tests](https://github.com/cimt-unia/bidslab/actions/workflows/tests.yml/badge.svg)](https://github.com/cimt-unia/bidslab/actions/workflows/tests.yml)
[![Lint](https://github.com/cimt-unia/bidslab/actions/workflows/lint.yml/badge.svg)](https://github.com/cimt-unia/bidslab/actions/workflows/lint.yml)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/cimt-unia/pyTermite/main.svg)](https://results.pre-commit.ci/latest/github/cimt-unia/pyTermite/main)

<!-- SPHINX-START-HERE -->

This repository contains a Python package to load, manipulate and write data that is in the
[BIDS](https://bids.neuroimaging.io/) (Brain Imaging Data Structure) format.

> **Note:** This project is not affiliated with or endorsed by the BIDS organization, but is intended to be a useful tool for working with BIDS datasets.

> **Warning:** BIDSlab is currently in pre-alpha development. The API may change significantly in future releases.
>
> This package is only intended for working with BIDS datasets. For information on BIDS itself, please refer to the official BIDS documentation at <https://bids.neuroimaging.io/>.
> <https://bids-specification.readthedocs.io/en/stable> is regarded as the single source of truth for the BIDS specification.
> Descriptions of BIDS entities and fields found in the API reference are merely intended as a convenience for users of BIDSlab and may be outdated or incomplete.
> In case of discrepancies, the official BIDS documentation should always be considered authoritative.

## Features

- **🧠 Multi-modality support** – Work with anatomical imaging, functional imaging, motion capture, and electromyography data in a unified, standardized format.
- **📦 Complete BIDS implementation (planned)** – Full support for the core BIDS specification with extensions.
- **⚡ Efficient data access** – Lazy-loading of data structures for memory-efficient handling of large datasets.
- **🔍 Comprehensive validation** – Built-in validation ensures datasets conform to BIDS standards and specifications.
- **🛠️ Developer-friendly API** – Clear, intuitive API with full type hints for seamless integration in Python workflows.
- **📚 Well-documented** – Extensive API documentation with numpy-style docstrings and examples throughout.

## Installation

Install BIDSlab from PyPI:

```bash
pip install bidslab
```

## Quick Start

Load and explore a BIDS dataset:

```python
from bidslab import load_dataset, write_dataset

# Load a BIDS dataset
dataset = load_dataset("/path/to/bids/dataset")

# Access dataset information
print(f"Dataset: {dataset.name}")
print(f"BIDS Version: {dataset.bids_version}")
print(f"Number of subjects: {len(dataset.participants)}")

# Explore the dataset structure
for participant in dataset.participants.values():
    for session in participant.sessions.values():
        for datatype in session.datatypes.values():
            print(
                f"  {participant.participant_id}/{session.session_id}/{datatype.datatype_name}"
            )

# Save modifications
write_dataset(dataset, "/path/to/output")
```

## Supported BIDS Modalities

**Core modalities (all planned)**

- Anatomical imaging (`anat`)
- Functional imaging (`func`)
- Diffusion imaging (`dwi`)
- Field maps (`fmap`)
- Perfusion imaging (`perf`)

**Extensions**

- [Motion capture](https://bidslab.readthedocs.io/en/latest/extensions.motion.html) – Optical, IMU, and video-based motion tracking
- [Electromyography](https://bidslab.readthedocs.io/en/latest/extensions.emg.html) – Surface and intramuscular EMG recordings
- [Electroencephalography](https://bidslab.readthedocs.io/en/latest/extensions.eeg.html) – Scalp EEG recordings
- [intracranial Electroencephalography](https://bidslab.readthedocs.io/en/latest/extensions.ieeg.html) – Intracranial EEG recordings

**Planned**

- NIBS – Non-invasive brain stimulation
- MEG – Magnetoencephalography
- MRS – Magnetic resonance spectroscopy
- NIRS – Near-infrared spectroscopy
- PET – Positron emission tomography
- And more...

<!-- SPHINX-END-HERE -->

## Documentation

The full documentation, including the API reference and the developer guide, is available on
Read the Docs at <https://bidslab.readthedocs.io/en/latest/>.

<!-- SPHINX-2-START-HERE -->

## Contributing

Contributions are welcome! Please read the
[contributing guidelines](https://github.com/cimt-unia/bidslab/blob/main/CONTRIBUTING.md)
and the [developer guide](https://bidslab.readthedocs.io/en/latest/developer_guide.html) before getting started.
To report a bug or suggest a feature, please open an
[issue](https://github.com/cimt-unia/bidslab/issues) on GitHub.

## About BIDS

The Brain Imaging Data Structure (BIDS) is a standard for organizing and describing
neuroimaging datasets. It provides a simple, standardized way to organize, describe,
and share neuroimaging and behavioral data.

Learn more about BIDS:

- **Official BIDS Specification**: <https://bids-specification.readthedocs.io/>
- **BIDS Community**: <https://bids.neuroimaging.io/>
- **BIDS Examples**: <https://github.com/bids-standard/bids-examples>

## License

BIDSlab is licensed under the BSD-3-Clause License. See the
[LICENSE](https://github.com/cimt-unia/BIDSlab/blob/main/LICENSE.txt) file in the repository for details.

## Citation

If you use BIDSlab in your research, please cite it appropriately. Citation information will be available once the package is formally released.
