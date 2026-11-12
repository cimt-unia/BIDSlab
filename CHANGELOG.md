## [unreleased]

### 🚀 Features

- Writing of emg json sidecars
- Add eeg modality
- Expand scans to include ieeg
- Add iEEG modality
- Emg writing, physio and stim recordings use Hardware and Columns
- Scans now work with all datatypes
- Add bug report and feature request templates
- Add ieeg_electrode_groups attribute

### 🐛 Bug Fixes

- Change physio and stim recordings to use columns and hardware
- Data loading of physio events, top level entity links for physio and stim
- Physio and stims files loaded from higher directories
- Add missing return types, type annotations, list comprehension
- Remove unused method get_entity_with_ending_from_file from helpers
- Allow stim_files to be "n/a" and therefore not be copied
- Include task information in emg json sidecar
- Scans columns and writing
- Eeg default run creation
- Eeg electrode loading
- String_manipulation to_snakecase matching multiple short forms
- Cog_po_id no longer has multiple underscores in eeg and ieeg
- Ieeg string manipulation, coordinate system
- Physio recordings now work with type eyetracking
- Remove edf+
- Mypy cleanup
- Ruff checks
- Update codecov.yml to enable informational coverage status for project and patch
- Update root path in test_dict_manipulation.py to prevent ruff errors due to tmp file path
- Update vulture min_confidence to 100 for stricter code analysis
- Add numpy to dependencies in pyproject.toml and default.txt
- Update pytest addopts in pyproject.toml to include junit output configuration
- Enable preview mode and adjust ruff linting rules in pyproject.toml
- Add junit.xml to .gitignore to prevent tracking of test output files
- Optimize string replacement for double underscores in string_manipulation.py
- Update noqa comments to ruff ignore directives in multiple files
- Remove unnecessary type ignore comments for URI validation
- Write json explicitly close the written file

### 🚜 Refactor

- Simplify datatype task creation
- Simplify session scans creation
- Improve get_data decorator
- Simplify entry dictionary creation in helpers.py
- Modernize generic type definitions
- Remove named arguments cog_atlas_id and cog_po_id
- Replace setattr calls with set_attr_from_dict for cleaner attribute assignment
- Remove task attribute
- Remove named arguments cog_atlas_id and cog_po_id in IEEGTask

### 📚 Documentation

- Add missing docstrings
- Fix EEGRun docstring
- Exclude duplicate members from automodule documentation
- Format type annotation of entity_class parameter in add_object_to_sequence docstring for docs rendering
- Fix docstring for runs property
- Update requirements/README.md to clarify requirements file generation and usage
- Update TODO list to include actionlint ignore removal note

### 🎨 Styling

- Add missing trailing comma in release dependencies
- Add type ignore comments for unreachable code in validation checks
- Remove unnecessary blank line in tox.ini

### ⚙️ Miscellaneous Tasks

- Add ANN204 to ruff ignore
- Update changelog
- Update pre-commit hooks to latest versions
- Update CI/CD workflows to enhance permissions and streamline processes
- Update pre-commit hook versions
- Exclude \_typing directory from coverage report
- Add commitlint configuration for conventional commits
- Add TODO for handling numpy data type in data loading
- Enhance Napoleon configuration with additional options and update type aliases
- Add type ignore for datalad.api import to prevent redefinition warning
- Add todos
- Add TODO comments to investigate clean_dict behavior and add test cases
- Add inline comments as reminder
- Add pandas-stubs to typing dependencies
- Update TODO list with additional tasks and notes
- Use self-repository syntax for reusable workflows
- Add support for maintaining Python package dependencies via uv in dependabot config
- Add dependency review action workflow
- Replace markdown issue templates with YAML configurations for bug and feature requests
- Add check-python-versions hook to pre-commit configuration
- Update dependency review action configuration and permissions
- Update classifiers for Python version support in pyproject.toml
- Add Python 3.14 to the testing matrix in GitHub Actions
- Add uv.lock file
- Add additional environments for developer tasks in tox
- Regenerate requirements files and remove obsolete ones
- Update generate_requirements hook to compile multiple requirement files with uv
- Update generate_todos entry to use uv for execution

## [0.3.0] - 2026-09-16

### 🚀 Features

- Add top-level entity task as property for class Acquisition
- Add class Run
- Add back-reference for top-level entity acquisition in class Run
- Add class TrackSys
- Add class Hardware and class Institution
- Add tracking_system_name attribute to class TrackSys
- Add back-reference for top-level entity task in class TrackSys
- Add class MotionAcquisition
- Add subclass MotionRun
- Add channels and reference frame for motion data
- Add functionality to load motion data
- Add back-reference for top-level entity acquisition during creation of Run classes in class BaseAcquisition
- \[**breaking**\] Add functionality to write dataset object to disk
- Automatically download datafiles with datalad
- Add settings to enable or disable rarely used features
- Add support for phenotype data
- Allow to write utf8 characters to json files
- Add events
- First draft for automatic scans detection
- Simple methods to filter datasets by participants, sessions and datatypes
- Add wrapper function to write datasets
- Add Recording and PhysioRecording entities
- Add option to suppress NotImplementedErrors
- Add classes for EMG modality
- Add typevar for task entities
- Add FileNotFoundWarning
- Add typevars for bids extensions
- Add missing acquisition setter to TrackSys class
- Make Recording a subclass of Entity
- Add option to use gzip compressed tsv files
- Add functionality to choose package for auto-fetching of data
- Add functionality to choose package for data loading
- Clean column_data dict after parsing participants.json
- Clean data dict in set_attr_from_dict
- Virtual entities, includes changes to run id
- Make classes Level and Run available in subpackage \_\_init\_\_.py
- Extend EMG functionality
- Stim first draft, relocate Event
- Writing of stimuli directory and stim files
- Add virtual entities to emg
- Writing of emg electrodes.tsv and channels.tsv
- Loading of events and stims files from higher directory levels
- First working draft of physio recordings, stim recordings
- Physioevents first working draft

### 🐛 Bug Fixes

- Add base_path argument during task instancing in method task.setter of class datatype
- Convert base_path argument of class TrackSys to pathlib.Path during initialization
- Set attribute tracking_system_name in class TrackSys correctly
- Build acquisition id from acquisition label
- Set attributes in class Run
- Write json files only if non empty
- Update 4f875dac
- Prevent column and level names from being modified into titlecase before writing to json
- Scans file order of directories for file loading
- Rework events to be consistent with existing datastructures
- Fix wrong loading of any combination of motiontask and tracksys, change data loading to use check_entity_mismatch
- Issue with run_id being just a number without run-
- Enforce run_id being an index of type integer
- Add missing imports for typing
- Reference_frame key can be missing in channel_dict
- Check if settings object is really a dict
- Adjust \_\_repr\_\_ of class Run to follow a073928e
- Writing of correct filenames on export if none are given, automatic scans detection
- Correct loading of scans during export
- Mypy cleanup
- Relocate events
- Load_dataset now possible with relative path
- Recording_id no longer written into physio and stim json
- Add docstring termination for manipulate_dictkeys
- Tests
- Use correct package name for version detection
- Do not add a new line at end of file when creating todos

### 🚜 Refactor

- Adjust skipping of titlecase conversion in function clean_dict
- Add name argument to function get_settings_values
- Use dicts instead of Sequences for downstream entities
- Use MutableSequence instead of Sequence
- Rename specs_description.py to specs_dataset.py
- Make class Recording usable for other modalities than physio
- Cleanup in \_\_init\_\_.py to finish refactoring
- Make abstractmethod write for class entity to protocol
- Use Mapping or MutableMapping instead of dict as type hint
- Make run_id an int instead of str
- Make variables of channel name extraction for dataframe column renaming more explicit
- Make dict cleating more general
- Change name to BIDSlab
- Change emg to use dicts for entities
- Change packagename in docs
- Relocate check_entity_mismatch
- Rename to bidslab in missing places
- Format to ruff rules
- Use setuptools-scm versioning
- Use set instead of list for get_matching_subpaths

### 📚 Documentation

- Document \_typing.base
- Improve docstrings in settings.py
- Improve stackoverflow citations
- Document helper functions
- Add CONTRIBUTING.md
- Document string manipulation functions
- Document checks.py
- Add module level docstring for exceptions.py
- Document io.py
- Document dict manipulation functions
- Document base.py
- Add sphinx documentation
- Document \_\_init\_\_.py files
- Improve documentation
- Conform to numpydoc lint
- Improve rst files for sphinx built documentation
- Update sphinx config
- Improve docstrings
- Improve docstrings for motion and emg modalities
- Improve docstrings for \_typing subpackage
- Comply with rstcheck
- Put commands in explicit code blocks
- Make docstrings comply with ruff
- Remove toctree entry for quick start guide on index page
- Fix example in docstring for EMGTask
- Update readme to reflect new name
- Fix documentation building
- Run mdformat
- Add codespell ignore
- Add missing docstrings
- Add that BIDSlab is not affiliated with BIDS organization

### 🎨 Styling

- Add type hints for static typing to class TrackSys
- Add type hints for static typing to function parse_motion_json_sidecar
- Add return type hint for tracking_systems getter in class MotionTask
- Reformat specs_misc.py
- Fix types
- Cleanup copyright notice
- Format code with ruff
- Add missing blank line
- Fix typo and remove second SPDX-Identifier

### 🧪 Testing

- Fix final assertion for test_tsv_json_files_multiple_json
- Change pytest fixture scope for tmp_root creation to 'module' to enable parallel tox runs
- Update tests for version check for 607f907c
- Add case for TermURL field entry
- Fix test_dataset fixture
- Expect sets when testing get_matching_subpaths

### ⚙️ Miscellaneous Tasks

- Add pandas-stubs dependency to mypy hook in .pre-commit-config.yaml
- Update .pre-commit-config.yaml
- Add script to generate todo list
- Update rstcheck config
- Bump minimal Python version to 3.12
- Add temp directory to .gitignore
- Update ruff config
- Add numpydoc config
- Update rstcheck config to suppress INFO level prints
- Update sphinx config
- Update coverage config
- Update pyproject.toml
- Update tox config
- Add cliff config for changelog generation
- Fix tox config
- Fix test dependency group
- Add datalad as dependency for tests
- Update requirements
- Update pre-commit config
- Clear old changelog
- Apply pre-commit auto fixes
- Add codecov config
- Add readthedocs config
- Add AGENTS.md file to describe documentation of the package
- Add .editorconfig
- Add TODO file and add it to docs
- Add depedency for git-cliff to build changelogs
- Update CHANGELOG.md
- Add vulture
- Use python 3.13 for pre-commit
- Add local todo list generation
- Update todos for docs
- Add mdformat config
- Add dependabot config
- Add ci workflows
- Add ruff ignore for non empty \_\_init\_\_.py
- Continue when lint and tests fail
- Remove mdformat config
- Update changelog
- Try upload to test pypi
- Build and install package when previous steps fail
- Try pypi release by setting condition to always
- Ignore ruf rule RUF106
- Add zizmor to pre-commit config
- Prepare release to PyPI
- Disable ruff preview rules to prevent errors from validate pyrpoject precommit hook

## [0.2.0] - 2025-09-25

### 🚀 Features

- Add MotionTasks
- Add Acquisitions
- Add automatic building of task_id
- Add add_entity_to_list helper to prepare for refactoring

### 🐛 Bug Fixes

- Rewrite top-level entity linking

### 💼 Other

- Fix dynamic versioning for setuptools in pyproject.toml

### 🚜 Refactor

- Move class Task to its own file
- Remove second SPDX-License-Identifier in utils/helpers
- Move Task definition to an abstract base class BaseTask and subclass Task and MotionTask
- Refactor warnings import
- Refactor tests for set_attr_from_dict
- Move functionality to get low-level entities from files to their own functions

### 🎨 Styling

- Remove extra whitespace in brackets of .pre-commit-config.yaml
- Add static typing for functions in helpers.py
- Add type hints for dataset paths
- Add 'str' as type hint for path argument in load_dataset

### 🧪 Testing

- Add test for c536e109
- Refactor sample classes to accept parameters in init method
- Add tests for 3a6097c1
- Change test_description_missing

### ⚙️ Miscellaneous Tasks

- *(release)* 0.2.0 (Automatically generated by python-semantic-release)

## [0.1.0.post1] - 2025-09-22

### ⚙️ Miscellaneous Tasks

- Fix changelog and version for 66b68782
- Fix License-Identifier in init file and readme

## [0.1.0] - 2025-09-22

### 🚀 Features

- Add functionality to load bids datasets

### ⚙️ Miscellaneous Tasks

- Initial commit
- Update .gitignore and pyproject.toml
- *(release)* 0.1.0 (Automatically generated by python-semantic-release)
