"""Various checks for BIDS datasets."""

#  Copyright (c) 2025 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

import pathlib
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any
from warnings import warn

from uritools import isuri

from bidslab.settings import get_settings_value
from bidslab.utils.exceptions import (
    FieldMissingWarning,
    FieldPresentError,
    FieldPresentWarning,
    FileMissingError,
    InvalidURIError,
    MultipleFilesFoundError,
    VersionMismatchError,
    VersionMismatchWarning,
)
from bidslab.utils.string_manipulation import to_titlecase

if TYPE_CHECKING:
    from bidslab.common.specs_dataset import Dataset


def check_readme(dataset: "Dataset", files: Sequence[pathlib.Path]) -> None:
    """
    Validate presence and uniqueness of the dataset README file.

    BIDS datasets are expected to provide a top-level README describing the dataset,
    usage considerations, or acquisition context. This function locates the first
    supported README variant and stores its path on the dataset object.

    Parameters
    ----------
    dataset : Dataset
        Dataset instance to update in place.
    files : Sequence[pathlib.Path]
        Paths representing the direct children of the dataset root.

    Raises
    ------
    MultipleFilesFoundError
        Raised when more than one README candidate is present and validation override
        is disabled.
    FileMissingError
        Raised when no README file is found and validation override is disabled.

    Warns
    -----
    FieldPresentWarning
        Emitted when multiple README files are present but validation override allows
        execution to continue.

    See Also
    --------
    :py:func:`check_files`
        Performs broader root-level dataset discovery.

    Notes
    -----
    Supported file names are ``README``, ``README.md``, ``README.txt``, and
    ``README.rst``. Exception raising can be overridden by the global
    ``OVERRIDE_VALIDATION`` setting.
    The function updates ``dataset.readme_path`` when a README is found.

    Examples
    --------
    >>> check_readme(dataset, list(dataset.root.iterdir()))
    >>> dataset.readme_path.name.startswith("README")
    True
    """
    readme_found = False

    for file in files:
        if re.match(r"^README(\.md|\.txt|\.rst)?$", file.name):
            if not readme_found:
                readme_found = True
            else:
                if not get_settings_value("OVERRIDE_VALIDATION"):
                    raise MultipleFilesFoundError(
                        "README[.md|.txt|.rst] file is already present."
                    )
                warn(
                    "Multiple README[.md|.txt|.rst] files found. Using the "
                    "first one found.",
                    FieldPresentWarning,
                )
                break
            dataset.readme_path = dataset.root / file

    if not readme_found and not get_settings_value("OVERRIDE_VALIDATION"):
        raise FileMissingError("README file is missing.")


def check_citation(dataset: "Dataset", files: Sequence[pathlib.Path]) -> None:
    """
    Validate a top-level ``CITATION.cff`` file and related metadata fields.

    When a dataset ships a citation file, some fields in ``dataset_description.json``
    become redundant or should be omitted in favor of the richer ``CITATION.cff``
    representation. This helper records the citation file path and enforces those
    relationships.

    Parameters
    ----------
    dataset : Dataset
        Dataset instance to inspect and update.
    files : Sequence[pathlib.Path]
        Paths representing the direct children of the dataset root.

    Raises
    ------
    FieldPresentError
        Raised when ``dataset.authors`` is already populated while ``CITATION.cff`` is
        present and validation override is disabled.

    Warns
    -----
    FieldPresentWarning
        Emitted when fields such as ``HowToAcknowledge`` or ``License`` are present in
        ``dataset_description`` even though ``CITATION.cff`` is available.

    See Also
    --------
    :py:func:`check_license`
        Performs related validation for the top-level license file.
    :py:func:`bidslab.utils.string_manipulation.to_titlecase`
        Formats dataset field names in warnings.

    Notes
    -----
    The function currently records the file path only; parsing and value propagation
    from ``CITATION.cff`` are marked as future work in the implementation.
    The function updates ``dataset.citation_path`` when a citation file is found.

    Examples
    --------
    >>> check_citation(dataset, list(dataset.root.iterdir()))
    >>> dataset.citation_path.name
    'CITATION.cff'
    """
    for file in files:
        if re.match(r"^CITATION\.cff$", file.name):
            if dataset.authors is not None and not get_settings_value(
                "OVERRIDE_VALIDATION"
            ):
                raise FieldPresentError(
                    "Field `Authors` must be omitted in `dataset_description` when "
                    "`CITATION.cff` is present."
                )

            dataset.citation_path = dataset.root / file
            # TODO: Parse CITATION.cff
            # TODO: overwrite Name and DatasetDOI

            for attr in ["how_to_acknowledge", "license", "references_and_links"]:
                if getattr(dataset, attr, None) is not None:
                    warn(
                        f"Field `{to_titlecase(attr)}` should be omitted in "
                        f"`dataset_description` when `CITATION.cff` is present.",
                        FieldPresentWarning,
                    )


def check_license(dataset: "Dataset", files: Sequence[pathlib.Path]) -> None:
    """
    Discover a LICENSE file and verify related descriptive metadata.

    Parameters
    ----------
    dataset : Dataset
        Dataset instance to update in place.
    files : Sequence[pathlib.Path]
        Paths representing the direct children of the dataset root.

    Warns
    -----
    FieldMissingWarning
        Emitted when a LICENSE file exists but the dataset description does not define
        a short ``License`` field and no citation file is present.

    See Also
    --------
    :py:func:`check_citation`
        Related validation for citation metadata that can overlap with licensing.

    Notes
    -----
    Supported file names are ``LICENSE``, ``LICENSE.md``, ``LICENSE.txt``, and
    ``LICENSE.rst``. The function does not yet compare the short license identifier in
    ``dataset_description.json`` against the actual file content.
    The function updates ``dataset.license_path`` when a LICENSE file is found.

    Examples
    --------
    >>> check_license(dataset, list(dataset.root.iterdir()))
    >>> dataset.license_path is not None
    True
    """
    for file in files:
        if re.match(r"^LICENSE(\.md|\.txt|\.rst)?$", file.name):
            dataset.license_path = dataset.root / file
            # TODO: Check if License in dataset_description matches LICENSE file content
            # TODO: Check if dataset.license is an abbreviation and warn if not
            if dataset.license is None and dataset.citation_path is None:
                warn(
                    "Field `License` is missing in `dataset_description` but LICENSE "
                    "file is present. Consider adding a short specification of the "
                    "license in `dataset_description`.",
                    FieldMissingWarning,
                )


def check_version(dataset: "Dataset", version: Any) -> None:
    """
    Compare a discovered BIDS version against the dataset target version.

    Parameters
    ----------
    dataset : Dataset
        Dataset instance that stores the expected BIDS version in
        ``dataset.bids_version``.
    version : Any
        Version value to validate. The runtime implementation requires a string.

    Raises
    ------
    TypeError
        Raised when ``version`` is not a string.
    VersionMismatchError
        Raised when the versions differ and neither ``IGNORE_VERSION`` nor
        ``OVERRIDE_VALIDATION`` permits continuation.

    Warns
    -----
    VersionMismatchWarning
        Emitted when versions differ and ``IGNORE_VERSION`` is enabled.

    See Also
    --------
    :py:class:`bidslab.utils.exceptions.VersionMismatchError`
        Exception raised for hard version mismatches.
    :py:class:`bidslab.utils.exceptions.VersionMismatchWarning`
        Warning emitted for tolerated mismatches.

    Notes
    -----
    The check is a direct string comparison and does not perform semantic version
    normalization.

    Examples
    --------
    >>> check_version(dataset, "1.10.0")
    """
    if not isinstance(version, str):
        raise TypeError(
            "BIDS version must be a string."
        )  # for mypy, TODO: change to static type
    if not dataset.bids_version == version:
        if get_settings_value("IGNORE_VERSION"):
            warn(
                f"BIDS version mismatch! Expected: {dataset.bids_version}, "
                f"Found: {version}. Compatibility issues may arise.",
                VersionMismatchWarning,
            )
        elif not get_settings_value("OVERRIDE_VALIDATION"):
            raise VersionMismatchError(
                f"BIDS version mismatch! Expected: {dataset.bids_version}, "
                f"Found: {version}."
            )


def check_dataset_description_present(dataset: "Dataset") -> None:
    """
    Ensure that ``dataset_description.json`` exists in the dataset root.

    Parameters
    ----------
    dataset : Dataset
        Dataset whose root directory should contain ``dataset_description.json``.

    Raises
    ------
    FileMissingError
        Raised when the file is absent and validation override is disabled.

    See Also
    --------
    :py:func:`check_files`
        Performs additional root-level discovery after this mandatory check.

    Notes
    -----
    This check enforces a core BIDS requirement for top-level dataset metadata.

    Examples
    --------
    >>> check_dataset_description_present(dataset)
    """
    if not (
        dataset.root / "dataset_description.json"
    ).exists() and not get_settings_value("OVERRIDE_VALIDATION"):
        raise FileMissingError("dataset_description.json file is missing.")


def check_if_valid_uri(uri: str) -> None:
    """
    Validate that a string is a syntactically valid URI.

    Parameters
    ----------
    uri : str
        Candidate URI string, such as a DOI resolver URL, RRID link, or project
        homepage.

    Raises
    ------
    InvalidURIError
        Raised when ``uri`` is not recognized as a valid URI and validation override
        is disabled.

    See Also
    --------
    :py:class:`bidslab.utils.exceptions.InvalidURIError`
        Exception used for invalid URI values.

    Notes
    -----
    Validation uses :py:func:`uritools.isuri` and therefore checks syntax only, not
    network reachability.

    Examples
    --------
    >>> check_if_valid_uri("https://bids.neuroimaging.io/")
    """
    if not isuri(uri) and not get_settings_value("OVERRIDE_VALIDATION"):
        raise InvalidURIError(f"Value '{uri}' is not a valid URI.")


def check_files(dataset: "Dataset", files: Sequence[pathlib.Path]) -> None:
    """
    Discover special top-level files and directories in a BIDS dataset.

    This helper coordinates root-level validation and path discovery. In addition to
    README validation, it records known optional resources such as ``CITATION.cff``,
    ``LICENSE``, ``CHANGES``, and standard directories like ``code`` or
    ``derivatives`` on the dataset object.

    Parameters
    ----------
    dataset : Dataset
        Dataset instance to update in place.
    files : Sequence[pathlib.Path]
        Paths representing the direct children of the dataset root.

    Raises
    ------
    MultipleFilesFoundError
        Propagated from :py:func:`check_readme` when multiple README files are found.
    FileMissingError
        Propagated from :py:func:`check_readme` when the README is missing and strict
        validation is active.

    Warnings
    --------
    The function mutates ``dataset`` and returns no value.

    See Also
    --------
    :py:func:`check_readme`
        Validates README presence before other discovery occurs.
    :py:func:`check_dataset_description_present`
        Mandatory root-level file check performed by callers before this helper.

    Notes
    -----
    :py:func:`check_license` and :py:func:`check_citation` are intentionally disabled
    in the current implementation because of side effects in the existing test suite.

    Examples
    --------
    >>> check_files(dataset, list(dataset.root.iterdir()))
    >>> dataset.derivatives_path is not None
    True
    """
    check_readme(dataset, files)
    # TODO: Enable these checks later --> rewriting of tests required due to
    #  side effects
    # check_license(dataset, files)
    # check_citation(dataset, files)
    for file in files:
        # if re.match(r"README(\..*)?", file.name):
        #     if dataset.readme_path is None:
        #         dataset.readme_path = dataset.root / file
        #     elif not get_settings_values("OVERRIDE_VALIDATION"):
        #         raise MultipleFilesFoundError("Multiple README files found.")
        #     else:
        #         warn(
        #             "Multiple README files found. Using the first one found: "
        #             f"{dataset.readme_path.name}",
        #             MultipleFilesFoundWarning,
        #         )
        if re.match(r"CITATION\.cff", file.name):
            dataset.citation_path = dataset.root / file
        elif re.match(r"LICENSE(\..*)?", file.name):
            dataset.license_path = dataset.root / file
        # TODO: Check how to handle multiple license files
        if re.match(r"CHANGES(\..*)?", file.name):
            dataset.changes_path = dataset.root / file
        elif file.name.startswith(r"sourcedata"):
            dataset.sourcedata_path = dataset.root / "sourcedata"
        elif file.name.startswith(r"code"):
            dataset.code_path = dataset.root / "code"
        elif file.name.startswith(r"stimuli"):
            dataset.stimuli_path = dataset.root / "stimuli"
        elif file.name.startswith(r"phenotype"):
            dataset.phenotype_path = dataset.root / "phenotype"
        elif file.name.startswith(r"derivatives"):
            dataset.derivatives_path = dataset.root / "derivatives"
