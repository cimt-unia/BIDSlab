"""Helper functions for various tasks in the BIDSlab package."""

#  Copyright (c) 2025 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

import json
import os
import pathlib
import re
import shutil
from collections.abc import Iterable, Iterator, MutableSequence, Sequence
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar, Union
from warnings import catch_warnings, simplefilter, warn

import edf_reader
import numpy as np
import pandas as pd

from bidslab._typing import EC, EE, MC, E, PEntity
from bidslab.settings import PackageFetching, PackageLoading, get_settings_value
from bidslab.utils.checks import (
    check_dataset_description_present,
    check_files,
)
from bidslab.utils.dict_manipulation import (
    ManipulateKeysOption,
    clean_dict,
)
from bidslab.utils.exceptions import (
    FieldNotValidError,
    FileTypeUnsupportedWarning,
    MultipleFilesFoundWarning,
    PathsSameWarning,
    TopLevelEntityNotLinkedWarning,
)
from bidslab.utils.string_manipulation import to_snakecase

if TYPE_CHECKING:
    from bidslab.common.specs_dataset import Dataset
    from bidslab.common.specs_misc import Event
    from bidslab.common.specs_summary import Scan

try:
    import datalad.api as dl
except ImportError:
    dl = None
    warn(
        "Datalad is not installed. Some functionalities may be limited.", ImportWarning
    )

T = TypeVar("T")

REQUIRED_ENTITIES_FOR_WRITING = {
    "tracksys",
    "task",
}


def set_attr_from_dict(obj: T, data: dict) -> None:
    """
    Set object attributes from a cleaned dictionary of values.

    The input mapping is normalized before assignment so that key names follow the
    internal snake_case attribute convention used throughout :py:mod:`bidslab`.
    Nested dictionaries can therefore be sourced from external metadata structures
    that use BIDS-style or title-cased field names.

    Parameters
    ----------
    obj : T
        Object whose existing attributes should be updated in place.
    data : dict
        Mapping of attribute names to values. Keys are sanitized with
        :py:func:`bidslab.utils.dict_manipulation.clean_dict` and converted to
        snake_case with :py:func:`bidslab.utils.string_manipulation.to_snakecase`
        before assignment.

    Returns
    -------
    None
        This function mutates ``obj`` directly and does not return a value.

    Raises
    ------
    FieldNotValidError
        Raised when at least one normalized key does not correspond to an attribute
        on ``obj``.

    See Also
    --------
    :py:func:`bidslab.utils.dict_manipulation.clean_dict`
        Normalizes nested dictionaries before assignment.
    :py:func:`bidslab.utils.string_manipulation.to_snakecase`
        Converts external field names to attribute-compatible identifiers.

    Notes
    -----
    Warnings of type
    :py:class:`bidslab.utils.exceptions.TopLevelEntityNotLinkedWarning` are silenced
    while assignments are performed.

    Examples
    --------
    >>> class Dummy:
    ...     participant_id = None
    >>> dummy = Dummy()
    >>> set_attr_from_dict(dummy, {"Participant ID": "01"})
    >>> dummy.participant_id
    '01'
    """
    data = clean_dict(
        data,
        skip_keys_to_manipulate=ManipulateKeysOption.ALL_KEYS_MANIPULATE,
        string_manipulation=to_snakecase,
        include_sequences=True,
    )
    for key, value in data.items():
        with catch_warnings():
            simplefilter("ignore", category=TopLevelEntityNotLinkedWarning)
            if hasattr(obj, key):
                setattr(obj, key, value)
            else:
                raise FieldNotValidError(
                    f"Field {key} is not valid in {obj.__class__.__name__}"
                ) from None


def parse_json_sidecar(sidecar_path: pathlib.Path) -> dict:
    """
    Parse a BIDS JSON sidecar file into a dictionary.

    JSON sidecars in BIDS datasets typically store acquisition metadata,
    coordinate-system descriptions, channel annotations, or other structured
    descriptors that accompany imaging or physiological data files. This helper
    provides a thin UTF-8-aware wrapper around :py:func:`json.load`.

    Parameters
    ----------
    sidecar_path : pathlib.Path
        Path to the JSON sidecar file. The path is expected to point to a readable
        UTF-8 encoded ``.json`` file.

    Returns
    -------
    dict
        Parsed JSON content as a Python dictionary. Typical return values include
        metadata such as ``{"SamplingFrequency": 1000, "StartTime": 0.0}``.

    Raises
    ------
    FileNotFoundError
        Raised when ``sidecar_path`` does not exist.
    json.JSONDecodeError
        Raised when the file content is not valid JSON.
    OSError
        Raised when the file cannot be opened for reading.

    See Also
    --------
    :py:func:`load_tsv_data`
        Loads tabular companion data that may reference the parsed metadata.
    :py:func:`get_tsv_json_files`
        Locates TSV/JSON file pairs in a directory.

    Notes
    -----
    The function does not validate keys against the BIDS specification; it only
    parses the file content.

    Examples
    --------
    >>> from pathlib import Path
    >>> metadata = parse_json_sidecar(Path("sub-01_task-rest_physio.json"))
    >>> metadata["SamplingFrequency"]
    1000
    """
    with sidecar_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_descriptive_tsv(tsv_path: pathlib.Path) -> Iterator[dict]:
    """
    Yield rows from a descriptive TSV file as dictionaries.

    This helper is intended for small, header-based TSV files in which the first
    line defines column names and each subsequent line describes one record. It is
    particularly useful for lightweight metadata tables where a streaming iterator
    is preferable to loading the full table into memory.

    Parameters
    ----------
    tsv_path : pathlib.Path
        Path to a tab-separated value file. The first row must contain column
        headers.

    Yields
    ------
    dict
        One dictionary per data row, keyed by the header names from the first line.
        Example yielded values include ``{"name": "Fp1", "type": "EEG"}``.

    Raises
    ------
    FileNotFoundError
        Raised when ``tsv_path`` does not exist.
    OSError
        Raised when the file cannot be opened.
    IndexError
        Raised when the TSV file is empty and therefore has no header row.

    See Also
    --------
    :py:func:`load_tsv_data`
        Loads TSV content into :py:class:`pandas.DataFrame` or
        :py:class:`numpy.ndarray`.

    Notes
    -----
    Rows are split on literal tab characters without additional type conversion.
    Missing trailing values remain absent because :py:func:`zip` stops at the
    shortest input.

    Examples
    --------
    >>> rows = list(parse_descriptive_tsv(pathlib.Path("participants.tsv")))
    >>> rows[0]["participant_id"]
    'sub-01'
    """
    with tsv_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
        headers = lines[0].strip().split("\t")
        for line in lines[1:]:
            entries = line.strip().split("\t")
            entry_dict = dict(zip(headers, entries, strict=False))
            yield entry_dict


def get_root_files(dataset: "Dataset") -> None:
    """
    Inspect the dataset root and run standard top-level checks.

    The helper collects direct children of the dataset root, verifies that the
    mandatory ``dataset_description.json`` file is available, and delegates further
    root-level discovery to :py:func:`bidslab.utils.checks.check_files`.

    Parameters
    ----------
    dataset : Dataset
        Dataset instance whose root directory should be inspected. The object is
        updated in place with discovered file and directory paths.

    Returns
    -------
    None
        This function mutates ``dataset`` and does not return a value.

    Raises
    ------
    FileMissingError
        Propagated when required BIDS root files are absent and validation is not
        overridden.
    OSError
        Raised when the dataset root cannot be enumerated.

    See Also
    --------
    :py:func:`bidslab.utils.checks.check_dataset_description_present`
        Verifies presence of ``dataset_description.json``.
    :py:func:`bidslab.utils.checks.check_files`
        Performs additional root-level discovery and validation.

    Notes
    -----
    The function has side effects on ``dataset`` because the invoked checks assign
    discovered paths such as README, LICENSE, or derivative directories.

    Examples
    --------
    >>> get_root_files(dataset)
    >>> dataset.readme_path is not None
    True
    """
    files = list(dataset.root.iterdir())
    check_dataset_description_present(dataset)

    check_files(dataset, files)


def get_matching_subpaths(
    path: pathlib.Path, matches: Sequence[str], root: pathlib.Path
) -> set[Path]:
    """
    Return parent paths that match one or more glob-like patterns.

    The function derives all parent components of ``path`` relative to ``root`` and
    tests each level, including ``path`` itself, against the supplied patterns. This
    is helpful when BIDS logic depends on whether a file resides below a particular
    directory hierarchy.

    Parameters
    ----------
    path : pathlib.Path
        Path whose parent chain should be inspected.
    matches : Sequence[str]
        Sequence of patterns accepted by :py:meth:`pathlib.PurePath.match`, such as
        ``("sub-*", "**/func")``.
    root : pathlib.Path
        Root directory relative to which parent levels are computed. ``path`` must be
        located inside this directory.

    Returns
    -------
    set[pathlib.Path]
        Matching path levels expressed as absolute paths below ``root``. An empty set
        indicates that no parent level satisfied any pattern.

    Raises
    ------
    ValueError
        Raised by :py:meth:`pathlib.Path.relative_to` when ``path`` is not contained
        in ``root``.

    See Also
    --------
    :py:func:`get_entity_from_file`
        Extracts BIDS entities from file names once a candidate path has been found.

    Notes
    -----
    The returned list may contain multiple entries for the same logical level if more
    than one pattern matches it.

    Examples
    --------
    >>> root = pathlib.Path("dataset")
    >>> path = root / "sub-01" / "ses-01" / "func"
    >>> get_matching_subpaths(path, ["sub-*", "*/func"], root)
    {PosixPath('dataset/sub-01'), PosixPath('dataset/sub-01/ses-01/func')}
    """
    # Get matching subpaths in the root directory
    paths = list(path.relative_to(root).parents) + [path]
    matching_subpaths = [
        root / dir_level
        for dir_level in paths
        for match in matches
        if dir_level.match(match)
    ]
    return set(matching_subpaths[::-1])


def get_entity_from_file(path: pathlib.Path, entity_name: str) -> dict[str, str]:
    """
    Extract one BIDS entity and its values from a file stem.

    BIDS file names encode metadata as ``entity-value`` pairs such as ``sub-01`` or
    ``task-rest``. This helper searches a file stem for a specific entity label and
    returns every match found for that label.

    Parameters
    ----------
    path : pathlib.Path
        Path whose stem should be inspected for BIDS entity tokens.
    entity_name : str
        Entity name to extract, for example ``"sub"`` or ``"task"``. Embedded spaces
        are removed before matching.

    Returns
    -------
    dict[str, str]
        Mapping from the matched entity name to its extracted value. Typical return
        values include ``{"sub": "01"}``. An empty dictionary indicates that the
        requested entity was not found.

    See Also
    --------
    :py:func:`bidslab.utils.string_manipulation.remove_special_characters`
        Normalizes strings that may later be used as entity values.

    Notes
    -----
    Only alphanumeric entity values are matched because the regular expression uses
    ``[a-zA-Z0-9]+``.

    Examples
    --------
    >>> path = pathlib.Path("sub-01_task-rest_physio.tsv.gz")
    >>> get_entity_from_file(path, "task")
    {'task': 'rest'}
    """
    entities = {}
    entity_name = entity_name.replace(" ", "")
    pattern = re.compile(rf"(?P<entity>({entity_name}))-(?P<value>[a-zA-Z0-9]+)")

    for match in pattern.finditer(path.stem):
        entities[match.group("entity")] = match.group("value")

    return entities


def get_tsv_json_files(
    path: pathlib.Path, file_name: str
) -> tuple[pathlib.Path | None, pathlib.Path | None]:
    """
    Locate TSV and JSON companions for a shared base name.

    Many BIDS tabular resources are stored as ``.tsv`` or ``.tsv.gz`` files with an
    optional sidecar JSON file that describes columns, units, or acquisition
    metadata. This helper scans one directory and returns the first supported file of
    each type while warning about duplicates or unsupported extensions.

    Parameters
    ----------
    path : pathlib.Path
        Directory in which the companion files should be searched.
    file_name : str
        Shared file name stem without extension, for example ``"participants"`` or
        ``"sub-01_task-rest_physio"``.

    Returns
    -------
    tuple[pathlib.Path | None, pathlib.Path | None]
        Two-item tuple ``(tsv_path, json_path)``. Each item is either the resolved
        path of the first matching supported file or ``None`` when no such file is
        present.

    Warns
    -----
    FileTypeUnsupportedWarning
        Emitted when a matching file has an unsupported extension.
    MultipleFilesFoundWarning
        Emitted when multiple supported TSV or JSON files are found.

    See Also
    --------
    :py:func:`parse_json_sidecar`
        Parses the returned JSON sidecar.
    :py:func:`load_tsv_data`
        Loads the returned TSV file into memory.
    :py:func:`get_edf_json_files`
        Equivalent lookup helper for EDF/BDF recordings.

    Notes
    -----
    ``.gz`` files are only accepted when their stem ends with ``.tsv`` so that
    ``.tsv.gz`` resources are distinguished from arbitrary gzip files.

    Examples
    --------
    >>> tsv_path, json_path = get_tsv_json_files(pathlib.Path("."), "participants")
    >>> tsv_path.suffix in {".tsv", ".gz"}
    True
    """
    files = path.glob(f"{file_name}.*")
    tsv_path = None
    json_path = None
    for file in files:
        match file.suffix:
            case ".tsv" | ".gz":
                if file.suffix == ".gz" and not file.stem.endswith(".tsv"):
                    warn(
                        f"File {file} has an unsupported extension. Only .tsv[.gz] and "
                        f".json are supported.",
                        FileTypeUnsupportedWarning,
                    )
                    continue
                if not tsv_path:
                    tsv_path = file
                else:
                    warn(
                        f"Multiple TSV files found for {file_name}. Using the first "
                        f"one found: {tsv_path.name}",
                        MultipleFilesFoundWarning,
                    )
                continue
            case ".json":
                if not json_path:
                    json_path = file
                else:
                    warn(
                        f"Multiple JSON files found for {file_name}. Using the first "
                        f"one found: {json_path.name}",
                        MultipleFilesFoundWarning,
                    )
                continue
            case _:
                warn(
                    f"File {file} has an unsupported extension. Only .tsv and .json "
                    f"are supported.",
                    FileTypeUnsupportedWarning,
                )
    return tsv_path, json_path


def get_edf_json_files(
    path: pathlib.Path, file_name: str
) -> tuple[pathlib.Path | None, pathlib.Path | None]:
    """
    Locate EDF/BDF recordings and their JSON companions.

    This helper is tailored to physiological recordings in BIDS datasets, where an
    ``.edf`` or ``.bdf`` signal file is commonly paired with a JSON sidecar that
    documents acquisition parameters such as sampling frequency, channel semantics,
    or recording start information.

    Parameters
    ----------
    path : pathlib.Path
        Directory in which the recording and sidecar should be searched.
    file_name : str
        Shared file name stem without extension.

    Returns
    -------
    tuple[pathlib.Path | None, pathlib.Path | None]
        Two-item tuple ``(edf_path, json_path)`` containing the first supported
        signal file and the first matching JSON sidecar, or ``None`` for missing
        items.

    Warns
    -----
    FileTypeUnsupportedWarning
        Emitted when an unsupported file type matches the stem.
    MultipleFilesFoundWarning
        Emitted when more than one EDF/BDF or JSON candidate exists.

    See Also
    --------
    :py:func:`load_edf_data`
        Reads the returned EDF/BDF recording into memory.
    :py:func:`parse_json_sidecar`
        Parses the returned sidecar metadata.
    :py:func:`get_tsv_json_files`
        Equivalent lookup helper for tabular BIDS resources.

    Examples
    --------
    >>> signal_path, meta_path = get_edf_json_files(
    ...     pathlib.Path("."),
    ...     "sub-01_task-rest_physio"
    ... )
    >>> signal_path.suffix in {".edf", ".bdf"}
    True
    """
    files = path.glob(f"{file_name}.*")
    edf_path = None
    json_path = None
    for file in files:
        match file.suffix:
            case ".edf" | ".bdf":
                if not edf_path:
                    edf_path = file
                else:
                    warn(
                        f"Multiple EDF or BDF files found for {file_name}. "
                        f"Using the first one found: {edf_path.name}",
                        MultipleFilesFoundWarning,
                    )
                continue
            case ".json":
                if not json_path:
                    json_path = file
                else:
                    warn(
                        f"Multiple JSON files found for {file_name}. Using the first "
                        f"one found: {json_path.name}",
                        MultipleFilesFoundWarning,
                    )
                continue
            case _:
                warn(
                    f"File {file} has an unsupported extension. Only .edf, "
                    f".bdf and .json are supported.",
                    FileTypeUnsupportedWarning,
                )
    return edf_path, json_path


def add_object_to_sequence(
    entity_list: MutableSequence,
    entity_class: "type[E] | type[EC] | type[EE] | type[MC] | type[Scan] | type[Event]",
    **kwargs: Any,
) -> None:
    """
    Instantiate an object and append it to a mutable sequence.

    This convenience helper centralizes the common pattern of creating an entity-like
    object from keyword arguments and adding it to an existing collection.

    Parameters
    ----------
    entity_list : MutableSequence
        Mutable sequence that will receive the created object.
    entity_class : type[E] | type[EC] | type[EE] | type[MC] | type[Scan]
        Concrete class to instantiate.
    **kwargs : Any
        Keyword arguments forwarded unchanged to ``entity_class``.

    Returns
    -------
    None
        The object is appended to ``entity_list`` in place.

    Raises
    ------
    TypeError
        Raised when ``entity_class`` cannot be instantiated with ``kwargs``.
    AttributeError
        Raised when ``entity_list`` does not provide an ``append`` method.

    See Also
    --------
    :py:func:`set_attr_from_dict`
        Populates an existing object from metadata rather than constructing a new one.

    Examples
    --------
    >>> class Entity:
    ...     def __init__(self, name):
    ...         self.name = name
    >>> items = []
    >>> add_object_to_sequence(items, Entity, name="example")
    >>> items[0].name
    'example'
    """
    entity_instance = entity_class(**kwargs)
    entity_list.append(entity_instance)


def append_path(
    input_path: os.PathLike | str,
    appendix: str,
) -> pathlib.Path:
    """
    Append text to the stem of a file path.

    The original suffix is preserved, making the helper suitable for generating
    derivative file names such as BIDS companion resources or entity-specific output
    paths.

    Parameters
    ----------
    input_path : os.PathLike | str
        Original path to transform.
    appendix : str
        Text appended directly to the existing stem before the suffix.

    Returns
    -------
    pathlib.Path
        New path with the modified stem. For example,
        ``append_path("signals.tsv.gz", "_channels")`` yields a path whose stem ends
        with ``"_channels"``.

    See Also
    --------
    :py:func:`write_entities`
        Uses this helper to derive entity-specific output paths.

    Examples
    --------
    >>> append_path("sub-01_task-rest.tsv", "_events")
    PosixPath('sub-01_task-rest_events.tsv')
    """
    path = pathlib.Path(input_path)
    return path.with_stem(path.stem + appendix)


def copy_file(
    source_path: os.PathLike | str,
    destination_path: os.PathLike | str,
) -> None:
    """
    Copy a file to a new location.

    Parameters
    ----------
    source_path : os.PathLike | str
        Existing file to copy.
    destination_path : os.PathLike | str
        Destination path for the copy. Parent directories must already exist.

    Raises
    ------
    FileNotFoundError
        Raised when ``source_path`` does not exist.
    OSError
        Raised when the underlying copy operation fails.

    Warns
    -----
    PathsSameWarning
        Emitted when source and destination resolve to the same path; the copy is
        skipped in this case.

    See Also
    --------
    :py:func:`write_json`
        Writes structured metadata files instead of copying an existing file.

    Notes
    -----
    Existing destination files are handled according to :py:func:`shutil.copy`.

    Examples
    --------
    >>> copy_file("participants.tsv", "backup/participants.tsv")
    """
    source_path = pathlib.Path(source_path)
    destination_path = pathlib.Path(destination_path)
    # TODO: add overwrite functionality / checks
    if source_path == destination_path:
        warn(
            "Source and destination paths are the same. Skipping copy.",
            PathsSameWarning,
        )
    elif source_path.exists():
        shutil.copy(source_path, destination_path)
    else:
        raise FileNotFoundError(f"Source file {source_path} does not exist.")


def write_entities(
    output_path: os.PathLike | str,
    entities: Union["Sequence[PEntity]", Iterable[PEntity]],
) -> None:
    """
    Write one or more portable entities to disk.

    When multiple entities are supplied, or when an entity belongs to the small set
    of required top-level identifiers, file names are disambiguated by appending the
    entity identifier to ``output_path`` before calling the entity's ``write``
    method.

    Parameters
    ----------
    output_path : os.PathLike | str
        Base path passed to each entity writer.
    entities : Sequence[PEntity]
        Sequence of writable entity objects implementing ``write(path)`` and the
        internal ``_entity_id`` and ``_entity_name`` attributes.

    See Also
    --------
    :py:func:`append_path`
        Builds disambiguated output paths for individual entities.

    Notes
    -----
    Entities named ``"tracksys"`` or ``"task"`` always receive a suffixed output path
    because they are listed in :data:`REQUIRED_ENTITIES_FOR_WRITING`.

    Examples
    --------
    >>> write_entities(pathlib.Path("coordsystem.json"), entities)
    """
    output_path = pathlib.Path(output_path)
    for entity in entities:
        path = (
            append_path(output_path, f"_{entity._entity_id}")
            if not entity._virtual_entity
            or entity._entity_name in REQUIRED_ENTITIES_FOR_WRITING
            else output_path
        )
        entity.write(path)


def write_json(content: dict[str, Any], output_path: os.PathLike | str) -> None:
    """
    Serialize a dictionary as formatted JSON.

    Parameters
    ----------
    content : dict[str, Any]
        Dictionary to serialize. Empty dictionaries are ignored and produce no file.
    output_path : os.PathLike | str
        Destination path for the JSON output.

    Raises
    ------
    TypeError
        Raised by :py:func:`json.dump` when ``content`` contains unsupported values.
    OSError
        Raised when the destination file cannot be opened or written.

    See Also
    --------
    :py:func:`parse_json_sidecar`
        Reads JSON files produced in the same general format.

    Notes
    -----
    Output is UTF-8 encoded, indented with four spaces, and written with
    ``ensure_ascii=False`` to preserve non-ASCII characters.

    Examples
    --------
    >>> write_json({"TaskName": "rest"}, "task-rest_bold.json")
    """
    output_path = pathlib.Path(output_path)
    if content:
        json.dump(
            content,
            output_path.open("w", encoding="utf-8"),
            indent=4,
            ensure_ascii=False,
        )


def get_data() -> Any:
    """
    Create a decorator that fetches missing data on demand.

    The returned decorator wraps loader functions that accept a keyword-only
    ``path`` argument. Before the wrapped loader is executed, the path is checked for
    existence and optionally retrieved through the package configured in
    ``DATASET_FETCHING_PACKAGE``.

    Returns
    -------
    Any
        Decorator that adds pre-load data retrieval behavior to a callable.

    Raises
    ------
    ValueError
        Raised by the wrapper when no supported fetching package is configured, when
        the configured package is unavailable, or when retrieval for the configured
        package is not implemented.

    See Also
    --------
    :py:func:`load_tsv_data`
        TSV loader decorated with this helper.
    :py:func:`load_edf_data`
        EDF loader decorated with this helper.

    Notes
    -----
    At present, only :py:mod:`datalad.api` retrieval is implemented.

    Examples
    --------
    >>> @get_data()
    ... def loader(*, path):
    ...     return path.exists()
    """

    def decorator(f):  # numpydoc ignore=GL08
        @wraps(f)
        def wrapper(*args, **kwargs):  # numpydoc ignore=GL08
            pkg_str = get_settings_value("DATASET_FETCHING_PACKAGE")
            if pkg_str in PackageFetching:
                pkg = eval(pkg_str)
            else:
                pkg = None
            path = kwargs.get("path")
            if not path.exists():
                if pkg:
                    if pkg.__name__ == "datalad.api":
                        pkg.get(path)
                    else:
                        raise ValueError(
                            f"Data retrieval for package {pkg.__name__} is not "
                            f"implemented."
                        )
                elif pkg is None:
                    raise ValueError(
                        f"Path '{path}' does not exist and no supported data fetching "
                        f"package is configured."
                    )
                else:
                    raise ValueError(
                        f"Package '{_pkg_str_to_pkg_name(pkg_str)}' is not available."
                    )
            return f(*args, **kwargs)

        return wrapper

    return decorator


@get_data()
def load_tsv_data(
    *, path: pathlib.Path, header: int | None = None
) -> pd.DataFrame | np.ndarray:
    """
    Load TSV data with the configured tabular backend.

    This function supports plain ``.tsv`` files as well as gzip-compressed
    ``.tsv.gz`` files when the pandas backend is selected. It is useful for BIDS
    tables such as ``events.tsv``, ``channels.tsv``, ``participants.tsv``, or other
    metadata matrices.

    Parameters
    ----------
    path : pathlib.Path
        Path to the TSV resource. If the file is missing, the surrounding
        :py:func:`get_data` decorator may attempt to fetch it.
    header : int | None, optional
        Row number to use as column labels when the pandas backend is active.
        ``None`` keeps the default pandas behavior of treating the file as having no
        header row. When the NumPy backend is active, the same value is used as the
        number of rows to skip. Default is ``None``.

    Returns
    -------
    pandas.DataFrame or numpy.ndarray
        Loaded table in the format selected by ``DATA_LOADING_PACKAGE``. Example
        return values include a :py:class:`pandas.DataFrame` with named columns or a
        numeric :py:class:`numpy.ndarray` for purely numeric tables.

    Raises
    ------
    ValueError
        Raised when the configured data loading backend is unsupported.
    FileNotFoundError
        Raised when the file is unavailable and cannot be fetched.
    pandas.errors.ParserError
        Raised when pandas cannot parse the TSV structure.
    OSError
        Raised when the file cannot be read.

    See Also
    --------
    :py:func:`parse_descriptive_tsv`
        Streams TSV rows as dictionaries instead of loading the full table.
    :py:func:`parse_json_sidecar`
        Reads metadata describing the loaded table.

    Notes
    -----
    The NumPy backend is appropriate only for homogeneous numeric tables because
    :py:func:`numpy.loadtxt` does not preserve mixed column types.

    Examples
    --------
    >>> table = load_tsv_data(path=pathlib.Path("participants.tsv"), header=0)
    >>> getattr(table, "shape", None)
    (3, 5)
    """
    data: pd.DataFrame | np.ndarray
    data_load_package = get_settings_value("DATA_LOADING_PACKAGE")
    if data_load_package == PackageLoading.PANDAS:
        if path.suffix == ".gz":
            try:
                data = pd.read_csv(path, sep="\t", header=header, compression="gzip")
            except pd.errors.EmptyDataError:
                data = pd.DataFrame()
        else:
            try:
                data = pd.read_csv(path, sep="\t", header=header)
            except pd.errors.EmptyDataError:
                data = pd.DataFrame()
    elif data_load_package == PackageLoading.NUMPY:
        data = np.loadtxt(path, delimiter="\t", skiprows=header or 0, encoding="utf-8")
    else:
        raise ValueError(
            f"Data loading for package {data_load_package} is not implemented."
        )
    return data


# TODO: write tests, especially with multi-channel data
@get_data()
def load_edf_data(*, path: pathlib.Path) -> pd.DataFrame | np.ndarray:
    """
    Load signal samples from an EDF or BDF recording.

    The function reads all time-series channels exposed by :mod:`edf_reader` and
    returns them in either NumPy or pandas form, depending on the configured loading
    backend. It is intended for physiological BIDS recordings such as EEG, EMG, or
    other biosignal data stored in European Data Format files.

    Parameters
    ----------
    path : pathlib.Path
        Path to the EDF or BDF recording. If the path is missing, the surrounding
        :py:func:`get_data` decorator may attempt to fetch it.

    Returns
    -------
    pandas.DataFrame or numpy.ndarray
        Multi-channel sample matrix. With the pandas backend the result is a
        :py:class:`pandas.DataFrame` whose rows correspond to samples and whose
        columns correspond to channels. With the NumPy backend the return value is the
        raw array produced by :mod:`edf_reader`.

    Raises
    ------
    FileNotFoundError
        Raised when the file is unavailable and cannot be fetched.
    OSError
        Raised when the recording cannot be opened or read.
    ValueError
        Raised when fetching or loading configuration is invalid.

    See Also
    --------
    :py:func:`get_edf_json_files`
        Locates EDF/BDF recordings and their sidecars.
    :py:func:`parse_json_sidecar`
        Parses metadata describing the loaded recording.

    Notes
    -----
    Channel labels are obtained from
    :py:meth:`edf_reader.EdfWrapper.read_ts_channel_basic_info`, and all channels are
    requested over their full available extent using ``[None, None]``.

    Examples
    --------
    >>> signal = load_edf_data(path=pathlib.Path("sub-01_task-rest_physio.edf"))
    >>> hasattr(signal, "shape")
    True
    """
    data: pd.DataFrame | np.ndarray

    reader = edf_reader.EdfWrapper(str(path))
    data = reader.read_ts_channels_uutc(
        [channel["name"] for channel in reader.read_ts_channel_basic_info()],
        [None, None],
    )

    data_load_package = get_settings_value("DATA_LOADING_PACKAGE")
    if data_load_package == PackageLoading.PANDAS:
        data = pd.DataFrame(data.T)

    return data


def _pkg_str_to_pkg_name(pkg_str: str) -> str:
    """
    Translate an enum-like settings string to a package name.

    Parameters
    ----------
    pkg_str : str
        String value retrieved from settings, such as ``"PackageLoading.PANDAS"``.

    Returns
    -------
    str
        Normalized package name such as ``"pandas"``, ``"numpy"``, or ``"datalad"``.

    Raises
    ------
    ValueError
        Raised when ``pkg_str`` is not recognized.

    See Also
    --------
    :py:func:`get_data`
        Uses this helper when reporting unavailable fetching packages.

    Examples
    --------
    >>> _pkg_str_to_pkg_name("PackageLoading.NUMPY")
    'numpy'
    """
    match pkg_str:
        case "PackageFetching.DATALAD":
            return "datalad"
        case "PackageLoading.PANDAS":
            return "pandas"
        case "PackageLoading.NUMPY":
            return "numpy"
        case _:
            raise ValueError(f"Unknown package string: {pkg_str}")
