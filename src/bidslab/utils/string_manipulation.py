"""String manipulation utilities."""

#  Copyright (c) 2025 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

import re

SHORT_FORMS = {
    "id": "ID",
    "uri": "URI",
    "url": "URL",
    "doi": "DOI",
    "bids": "BIDS",
    "rrid": "RRID",
    "accel": "ACCEL",
    "angaccel": "ANGACCEL",
    "gyro": "GYRO",
    "jntang": "JNTANG",
    "latency": "LATENCY",
    "magn": "MAGN",
    "misc": "MISC",
    "ornt": "ORNT",
    "pos": "POS",
    "vel": "VEL",
    "hed": "HED",
    "emg": "EMG",
    "eeg": "EEG",
    "ecg": "ECG",
    "eog": "EOG",
    "po": "PO",
    "ecog": "ECOG",
    "seeg": "SEEG",
    "ieeg": "iEEG",
}


def to_titlecase(string: str) -> str:
    """
    Convert a string to TitleCase while preserving known acronyms.

    This helper is primarily used to map internal snake_case field names to the
    title-cased keys commonly found in BIDS JSON metadata, while keeping tokens such
    as ``BIDS``, ``DOI``, or ``RRID`` uppercase.

    Parameters
    ----------
    string : str
        Input string containing words separated by underscores or spaces.

    Returns
    -------
    str
        Title-cased string with recognized short forms preserved. Example return
        values include ``"DatasetDOI"`` and ``"SamplingFrequency"``.

    See Also
    --------
    :py:func:`to_snakecase`
        Converts field names in the opposite direction.

    Notes
    -----
    The function splits only on underscores and literal spaces. Existing camelCase or
    punctuation is not normalized beyond that behavior.

    Examples
    --------
    >>> to_titlecase("dataset_doi")
    'DatasetDOI'
    >>> to_titlecase("bids uri")
    'BIDSURI'
    """
    parts = re.split(r"[_ ]", string)
    parts = [
        SHORT_FORMS[part.lower()] if part.lower() in SHORT_FORMS else part.title()
        for part in parts
    ]
    return "".join(parts)


def to_snakecase(string: str) -> str:
    """
    Convert a mixed-case string to snake_case while preserving BIDS acronyms.

    The function is designed for field-name normalization when converting external
    metadata keys such as ``DatasetDOI`` or ``SamplingFrequency`` to internal Python
    attribute names.

    Parameters
    ----------
    string : str
        Input string in TitleCase, camelCase, or a partially normalized form.

    Returns
    -------
    str
        Snake-cased representation in lowercase. Example return values include
        ``"dataset_doi"`` and ``"sampling_frequency"``.

    See Also
    --------
    :py:func:`to_titlecase`
        Converts normalized identifiers back to BIDS-style key casing.

    Notes
    -----
    Known acronyms are isolated before generic case-splitting occurs. Special-case
    handling prevents accidental splitting of tokens such as ``ANGACCEL`` or parts of
    ``RRID`` and ``BIDS``.

    Examples
    --------
    >>> to_snakecase("DatasetDOI")
    'dataset_doi'
    >>> to_snakecase("SamplingFrequency")
    'sampling_frequency'
    """
    for value in sorted(SHORT_FORMS.values(), key=len, reverse=True):
        string = re.sub(value, f" {value.lower()} ", string)
    string = re.sub(r"[_ ]", "_", string.strip())
    string = re.sub(r"__", "_", string)
    string = re.sub(r"([a-z])([A-Z])", r"\1_\2", string)
    return string.lower()


def remove_special_characters(string: str) -> str:
    """
    Replace non-alphanumeric characters with plus-separated tokens.

    This helper is useful when free-text labels need to be converted into compact,
    delimiter-stable fragments that can be embedded in identifiers or search terms.

    Parameters
    ----------
    string : str
        Input string to sanitize.

    Returns
    -------
    str
        Sanitized string in which contiguous runs of non-alphanumeric characters are
        collapsed into ``"+"`` separators. For example, ``"Left / Right"`` becomes
        ``"Left+Right"``.

    See Also
    --------
    :py:func:`to_snakecase`
        Produces Python-friendly identifiers rather than plus-separated labels.

    Notes
    -----
    Leading and trailing separators are removed from the final output.

    Examples
    --------
    >>> remove_special_characters("EEG (resting-state)")
    'EEG+resting+state'
    """
    string = re.sub(r"[^a-zA-Z0-9]", " ", string)
    return re.sub(r"\s+", "+", string).strip("+")
