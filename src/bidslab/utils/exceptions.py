"""Custom exceptions and warnings for BIDSlab."""

#  Copyright (c) 2025 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause


class FieldEntryNotValidError(Exception):
    """
    Exception raised when an individual metadata value is semantically invalid.

    This exception is suitable for situations in which a field is present but its
    value violates allowed content constraints, controlled vocabularies, or expected
    formatting rules.

    See Also
    --------
    :py:class:`FieldNotValidError`
        Raised when the field name itself is not valid.
    :py:class:`FieldMissingError`
        Raised when a required field is absent entirely.

    Notes
    -----
    Use this exception when the field itself is recognized but one specific entry is
    unacceptable.

    Examples
    --------
    >>> raise FieldEntryNotValidError("SamplingFrequency must be positive.")
    Traceback (most recent call last):
    ...
    FieldEntryNotValidError: SamplingFrequency must be positive.
    """

    pass


class FieldMissingError(Exception):
    """
    Exception raised when a required metadata field is absent.

    This error typically signals a BIDS compliance violation for mandatory entries in
    JSON sidecars, TSV columns, or ``dataset_description.json``.

    See Also
    --------
    :py:class:`FieldMissingWarning`
        Warning counterpart for recommended but non-mandatory fields.
    :py:class:`FileMissingError`
        Raised when the missing resource is a file rather than a field.

    Notes
    -----
    Prefer this exception over :py:class:`FileMissingError` when the missing item is a
    logical field within an otherwise accessible file or object.

    Examples
    --------
    >>> raise FieldMissingError("Required field 'Name' is missing.")
    Traceback (most recent call last):
    ...
    FieldMissingError: Required field 'Name' is missing.
    """

    pass


class FieldMissingWarning(Warning):
    """
    Warning raised when a recommended metadata field is absent.

    This warning is useful for soft validation paths where the dataset remains usable
    but would benefit from additional descriptive metadata.

    See Also
    --------
    :py:class:`FieldMissingError`
        Hard-failure counterpart for required fields.

    Notes
    -----
    Typical examples include optional BIDS fields that improve interoperability or
    documentation quality without being strictly required.

    Examples
    --------
    >>> import warnings
    >>> warnings.warn("Consider adding License.", FieldMissingWarning)
    """

    pass


class FieldNotValidError(Exception):
    """
    Exception raised when a field name or attribute is not recognized.

    The exception is commonly used when external metadata contains keys that cannot
    be mapped to supported attributes or BIDS fields.

    See Also
    --------
    :py:class:`FieldEntryNotValidError`
        Raised when the field exists but contains an invalid value.
    :py:class:`FieldPresentError`
        Raised when a field is present even though it must be omitted.

    Notes
    -----
    Use this exception for invalid field identifiers rather than invalid values.

    Examples
    --------
    >>> raise FieldNotValidError("Field FooBar is not valid in Dataset")
    Traceback (most recent call last):
    ...
    FieldNotValidError: Field FooBar is not valid in Dataset
    """

    pass


class FieldPresentError(Exception):
    """
    Exception raised when a disallowed field is present.

    This typically occurs when two metadata sources are mutually exclusive and one of
    them should be omitted according to project or BIDS rules.

    See Also
    --------
    :py:class:`FieldPresentWarning`
        Warning variant for discouraged but tolerated fields.
    :py:class:`FieldNotValidError`
        Raised when the field name is unsupported rather than merely disallowed here.

    Notes
    -----
    In strict validation flows this class signals a hard error, whereas
    :py:class:`FieldPresentWarning` may be used for tolerated cases.

    Examples
    --------
    >>> raise FieldPresentError("Authors must be omitted when CITATION.cff is present.")
    Traceback (most recent call last):
    ...
    FieldPresentError: Authors must be omitted when CITATION.cff is present.
    """

    pass


class FieldPresentWarning(Warning):
    """
    Warning raised when a field is present but should ideally be omitted.

    The warning supports non-fatal validation scenarios in which duplicate or
    redundant metadata is tolerated but highlighted for cleanup.

    See Also
    --------
    :py:class:`FieldPresentError`
        Hard-failure counterpart for disallowed fields.

    Examples
    --------
    >>> import warnings
    >>> warnings.warn(
    ...     "License should be omitted when CITATION.cff is present.",
    ...     FieldPresentWarning
    ... )
    """

    pass


class BadDirectoryStructureError(Exception):
    """
    Exception raised when the directory structure does not follow the BIDS standard.

    Typical use cases include any time an objects
    needs to access files located in higher directories.
    """

    pass


class FileMissingError(Exception):
    """
    Exception raised when a required file is absent.

    Typical use cases include missing BIDS root files such as
    ``dataset_description.json`` or other mandatory companions.

    See Also
    --------
    :py:class:`FileMissingWarning`
        Warning counterpart for recommended files.
    :py:class:`FieldMissingError`
        Raised when the missing item is a field instead of a file.

    Notes
    -----
    Use this exception for filesystem-level requirements rather than missing metadata
    within an existing file.

    Examples
    --------
    >>> raise FileMissingError("dataset_description.json file is missing.")
    Traceback (most recent call last):
    ...
    FileMissingError: dataset_description.json file is missing.
    """

    pass


class FileMissingWarning(Warning):
    """
    Warning raised when a recommended file is absent.

    This class is intended for optional documentation or auxiliary files whose
    absence should be communicated without aborting processing.

    See Also
    --------
    :py:class:`FileMissingError`
        Hard-failure counterpart for required files.

    Examples
    --------
    >>> import warnings
    >>> warnings.warn("CHANGES file is recommended.", FileMissingWarning)
    """

    pass


class FileNotFoundWarning(Warning):
    """
    Warning raised when an expected file path cannot be resolved.

    Unlike :py:class:`FileMissingError`, this warning is appropriate when the missing
    path does not necessarily invalidate the dataset but may affect optional
    processing steps.

    See Also
    --------
    :py:class:`FileMissingError`
        Exception for required missing files.

    Examples
    --------
    >>> import warnings
    >>> warnings.warn("Optional calibration file was not found.", FileNotFoundWarning)
    """

    pass


class FileTypeUnsupportedWarning(Warning):
    """
    Warning raised when a discovered file uses an unsupported extension.

    This warning is typically emitted during companion-file discovery when a file
    shares the expected base name but does not conform to the supported set of file
    formats.

    See Also
    --------
    :py:class:`MultipleFilesFoundWarning`
        Warning raised when too many supported candidates are found.

    Examples
    --------
    >>> import warnings
    >>> warnings.warn(
    ...     "Only .tsv[.gz] and .json are supported.",
    ...     FileTypeUnsupportedWarning
    ... )
    """

    pass


class InvalidURIError(Exception):
    """
    Exception raised when a URI fails syntactic validation.

    This exception is used for metadata values that should be resolvable or at least
    syntactically well-formed URIs, such as homepage links, DOI URLs, or ontology
    references.

    See Also
    --------
    :py:class:`FieldEntryNotValidError`
        More general exception for semantically invalid field values.

    Notes
    -----
    The associated checks validate URI syntax, not whether the referenced resource is
    reachable.

    Examples
    --------
    >>> raise InvalidURIError("Value 'not a url' is not a valid URI.")
    Traceback (most recent call last):
    ...
    InvalidURIError: Value 'not a url' is not a valid URI.
    """

    pass


class MisusedDecoratorError(Exception):
    """
    Exception raised when a decorator is applied incorrectly.

    This exception is intended for internal use in BIDSlab to catch programming errors
    where decorators are misapplied to functions or methods that do not meet the
    expected signature or context.

    Examples
    --------
    >>> raise MisusedDecoratorError(
    ...     "Decorator @bids_validator applied to non-callable."
    ... )
    Traceback (most recent call last):
    ...
    MisusedDecoratorError: Decorator @bids_validator applied to non-callable.
    """

    pass


class MultipleFilesFoundError(Exception):
    """
    Exception raised when more than one mutually exclusive file is present.

    This typically indicates that the dataset contains ambiguous top-level resources,
    such as multiple README files, where only one authoritative file should exist.

    See Also
    --------
    :py:class:`MultipleFilesFoundWarning`
        Non-fatal counterpart used when validation is overridden.

    Examples
    --------
    >>> raise MultipleFilesFoundError("README file is already present.")
    Traceback (most recent call last):
    ...
    MultipleFilesFoundError: README file is already present.
    """

    pass


class MultipleFilesFoundWarning(Warning):
    """
    Warning raised when multiple candidate files are found but execution continues.

    This warning usually indicates that the first discovered matching file is used as
    a fallback while the remaining candidates are ignored.

    See Also
    --------
    :py:class:`MultipleFilesFoundError`
        Exception counterpart for strict validation.

    Examples
    --------
    >>> import warnings
    >>> warnings.warn(
    ...     "Multiple JSON files found. Using the first one found.",
    ...     MultipleFilesFoundWarning
    ... )
    """

    pass


class PathsSameWarning(Warning):
    """
    Warning raised when source and destination paths are identical.

    It is typically emitted by file-copy helpers to indicate that the requested
    operation would be a no-op and has therefore been skipped.

    See Also
    --------
    :py:class:`FileNotFoundWarning`
        Warning for missing optional file paths.

    Examples
    --------
    >>> import warnings
    >>> warnings.warn("Source and destination paths are the same.", PathsSameWarning)
    """

    pass


class TopLevelEntityNotLinkedWarning(Warning):
    """
    Warning raised when a top-level entity cannot be linked automatically.

    This warning is relevant for object-population workflows in which entity metadata
    may be partially known but not yet connected to the corresponding top-level data
    structures.

    See Also
    --------
    :py:class:`FieldNotValidError`
        Exception raised when the target field itself is invalid.

    Notes
    -----
    Some helper functions intentionally suppress this warning during bulk attribute
    assignment.

    Examples
    --------
    >>> import warnings
    >>> warnings.warn(
    ...     "Top-level entity could not be linked.",
    ...     TopLevelEntityNotLinkedWarning
    ... )
    """

    pass


class VersionMismatchError(Exception):
    """
    Exception raised when expected and observed versions differ.

    In BIDSlab this is primarily used for BIDS specification version mismatches that
    can affect compatibility or validation outcomes.

    See Also
    --------
    :py:class:`VersionMismatchWarning`
        Warning counterpart for tolerated mismatches.

    Examples
    --------
    >>> raise VersionMismatchError("Expected 1.10.0, found 1.9.0.")
    Traceback (most recent call last):
    ...
    VersionMismatchError: Expected 1.10.0, found 1.9.0.
    """

    pass


class VersionMismatchWarning(Warning):
    """
    Warning raised when versions differ but processing is allowed to continue.

    This warning communicates a compatibility risk without enforcing a hard stop.

    See Also
    --------
    :py:class:`VersionMismatchError`
        Exception raised for non-tolerated version mismatches.

    Examples
    --------
    >>> import warnings
    >>> warnings.warn("BIDS version mismatch detected.", VersionMismatchWarning)
    """

    pass
