"""Utility functions for manipulating dictionaries."""

#  Copyright (c) 2025 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

import pathlib
from collections.abc import Callable, MutableMapping, Sequence
from dataclasses import asdict
from enum import IntEnum
from typing import TYPE_CHECKING

from bidslab.utils.string_manipulation import to_titlecase

if TYPE_CHECKING:
    from bidslab.common.specs_misc import Level


class ManipulateKeysOption(IntEnum):
    """
    Enumeration controlling how dictionary keys are transformed.

    The enum is used by :py:func:`clean_dict` to decide whether key normalization
    should be applied to all levels, skipped entirely, or restricted to nested
    dictionaries.

    Attributes
    ----------
    NO_MANIPULATION
        Preserve all keys exactly as provided.
    ALL_KEYS_MANIPULATE
        Apply the configured string transformation to all dictionary keys.
    SKIP_TOP_LEVEL_MANIPULATE
        Preserve top-level keys while transforming nested dictionary keys.

    See Also
    --------
    :py:func:`clean_dict`
        Consumer of these key-transformation policies.

    Examples
    --------
    >>> ManipulateKeysOption.ALL_KEYS_MANIPULATE
    <ManipulateKeysOption.ALL_KEYS_MANIPULATE: 0>
    """

    NO_MANIPULATION = -1
    ALL_KEYS_MANIPULATE = 0
    SKIP_TOP_LEVEL_MANIPULATE = 1


def manipulate_dictkeys(
    dict_input: dict,
    string_manipulation: Callable[[str], str] = to_titlecase,
) -> dict:
    """
    Recursively transform dictionary keys with a string conversion function.

    Parameters
    ----------
    dict_input : dict
        Dictionary whose keys should be transformed.
    string_manipulation : Callable[[str], str], optional
        Callable applied to each key. The default,
        :py:func:`bidslab.utils.string_manipulation.to_titlecase`, is suitable for
        converting internal field names to BIDS-style metadata keys.

    Returns
    -------
    dict
        New dictionary with transformed keys. Values that are nested dictionaries are
        processed recursively.

    See Also
    --------
    :py:func:`clean_dict`
        Applies this transformation as one step of broader dictionary cleanup.
    :py:func:`bidslab.utils.string_manipulation.to_titlecase`
        Default key-conversion function.

    Notes
    -----
    The ``Levels`` key receives special handling so that nested level descriptions are
    transformed without altering the top-level semantic structure expected by BIDS.

    Examples
    --------
    >>> manipulate_dictkeys({"sampling_frequency": 1000})
    {'SamplingFrequency': 1000}
    """
    dict_output = {}
    for key, value in list(dict_input.items()):
        if key == "Levels":
            if all(isinstance(v, dict) for v in value.values()):
                for v_key, v_value in value.items():
                    value[v_key] = manipulate_dictkeys(
                        v_value, string_manipulation=string_manipulation
                    )
            dict_output[string_manipulation(key)] = value
            continue
        if isinstance(value, dict):
            dict_output[string_manipulation(key)] = manipulate_dictkeys(
                value, string_manipulation=string_manipulation
            )
        else:
            dict_output[string_manipulation(key)] = value

    return dict_output


def clean_dict(
    dict_input: dict,
    skip_keys_to_manipulate: ManipulateKeysOption = (
        ManipulateKeysOption.ALL_KEYS_MANIPULATE
    ),
    include_sequences: bool = False,
    string_manipulation: Callable[[str], str] = to_titlecase,
) -> dict:
    """
    Clean a dictionary for serialization or metadata export.

    The cleaning pipeline removes ``None`` values, drops private keys, converts
    :py:class:`pathlib.Path` objects to strings, removes the reserved ``root`` key,
    and optionally transforms keys to a target naming convention.

    Parameters
    ----------
    dict_input : dict
        Dictionary to clean.
    skip_keys_to_manipulate : ManipulateKeysOption, optional
        Policy controlling whether keys are transformed. ``NO_MANIPULATION`` keeps all
        keys unchanged, ``ALL_KEYS_MANIPULATE`` transforms every key, and
        ``SKIP_TOP_LEVEL_MANIPULATE`` preserves only the top-level keys. Default is
        :py:attr:`ManipulateKeysOption.ALL_KEYS_MANIPULATE`.
    include_sequences : bool, optional
        If ``True``, dictionaries contained inside list values are cleaned
        recursively. Default is ``False``.
    string_manipulation : Callable[[str], str], optional
        Function used to transform keys when manipulation is enabled. Default is
        :py:func:`bidslab.utils.string_manipulation.to_titlecase`.

    Returns
    -------
    dict
        Cleaned dictionary ready for JSON export or object population.

    Raises
    ------
    ValueError
        Raised when ``skip_keys_to_manipulate`` is not a valid
        :py:class:`ManipulateKeysOption` member.

    See Also
    --------
    :py:func:`delete_none_from_dict`
        Removes ``None`` values recursively.
    :py:func:`delete_private_fields_from_dict`
        Removes keys whose names start with ``"_"``.
    :py:func:`dict_paths_to_strings`
        Converts :py:class:`pathlib.Path` values to strings.
    :py:func:`manipulate_dictkeys`
        Applies key renaming after structural cleanup.

    Notes
    -----
    The cleanup is partly in-place because :py:func:`delete_none_from_dict` mutates
    nested dictionaries while removing ``None`` values.

    Examples
    --------
    >>> clean_dict({
    ...     "root": pathlib.Path("."),
    ...     "sampling_frequency": 1000,
    ...     "note": None
    ... })
    {'SamplingFrequency': 1000}
    """
    dict_output = delete_none_from_dict(dict_input)
    dict_output = delete_private_fields_from_dict(dict_output)
    dict_output = dict_paths_to_strings(dict_output)
    _ = dict_output.pop("root", None)
    # Will raise DeprecationWarning due to __contains__ raising TypeError in Python
    # versions < 3.12
    if skip_keys_to_manipulate not in ManipulateKeysOption:
        raise ValueError(
            f"keys_to_titlecase must be -1, 0, or 1, got {skip_keys_to_manipulate}"
        )
    if skip_keys_to_manipulate == ManipulateKeysOption.ALL_KEYS_MANIPULATE:
        dict_output = manipulate_dictkeys(
            dict_output, string_manipulation=string_manipulation
        )
    if skip_keys_to_manipulate == ManipulateKeysOption.SKIP_TOP_LEVEL_MANIPULATE:
        for key, value in list(dict_output.items()):
            dict_output[key] = manipulate_dictkeys(
                value, string_manipulation=string_manipulation
            )
    if include_sequences:
        for key, value in dict_output.items():
            match value:
                case list() if any(isinstance(item, dict) for item in value):
                    dict_output[key] = [
                        (
                            clean_dict(
                                item,
                                skip_keys_to_manipulate,
                                include_sequences,
                                string_manipulation,
                            )
                            if isinstance(item, dict)
                            else item
                        )
                        for item in value
                    ]
    return dict_output


def dict_paths_to_strings(dict_input: dict) -> dict:
    """
    Recursively convert :py:class:`pathlib.Path` values to strings.

    Parameters
    ----------
    dict_input : dict
        Dictionary whose values may include nested dictionaries and path objects.

    Returns
    -------
    dict
        Copy of the input structure in which every :py:class:`pathlib.Path` value has
        been replaced by its string representation.

    See Also
    --------
    :py:func:`clean_dict`
        Incorporates this conversion into a broader cleanup pipeline.

    Notes
    -----
    Non-dictionary containers other than direct path values are preserved unchanged.

    Examples
    --------
    >>> dict_paths_to_strings({"path": pathlib.Path("sub-01")})
    {'path': 'sub-01'}
    """
    dict_output: dict[str, dict | str] = {}
    for key, value in list(dict_input.items()):
        if isinstance(value, dict):
            dict_output[key] = dict_paths_to_strings(value)
        else:
            if isinstance(value, pathlib.Path):
                dict_output[key] = value.as_posix()
            else:
                dict_output[key] = value

    return dict_output


def delete_private_fields_from_dict(dict_input: MutableMapping) -> dict:
    """
    Remove private keys from a nested mapping.

    Parameters
    ----------
    dict_input : MutableMapping
        Mapping to clean. Keys beginning with ``"_"`` are treated as private.

    Returns
    -------
    dict
        New dictionary without private keys. Nested dictionaries are processed
        recursively.

    See Also
    --------
    :py:func:`delete_none_from_dict`
        Removes missing values rather than private keys.
    :py:func:`clean_dict`
        Uses this helper during metadata normalization.

    Notes
    -----
    Only non-dictionary values are tested directly; nested mappings are traversed and
    rebuilt.

    Examples
    --------
    >>> delete_private_fields_from_dict({"name": "rest", "_internal": 1})
    {'name': 'rest'}
    """
    dict_output = {}
    for key, value in list(dict_input.items()):
        if isinstance(value, dict):
            dict_output[key] = delete_private_fields_from_dict(value)
        else:
            if not key.startswith("_"):
                dict_output[key] = value

    return dict_output


def delete_none_from_dict(dict_input: dict) -> dict:
    """
    Remove ``None`` values recursively from a dictionary structure.

    Parameters
    ----------
    dict_input : dict
        Dictionary to clean. Nested dictionaries and dictionaries inside lists are
        processed recursively.

    Returns
    -------
    dict
        The same dictionary instance with all ``None``-valued keys removed.

    See Also
    --------
    :py:func:`clean_dict`
        Wraps this helper with additional cleanup steps.

    Notes
    -----
    This function mutates ``dict_input`` in place. Lists are traversed only to clean
    dictionary items they contain; other list items are left unchanged.

    Examples
    --------
    >>> delete_none_from_dict({"a": 1, "b": None, "c": {"d": None, "e": 2}})
    {'a': 1, 'c': {'e': 2}}
    """
    # Source - https://stackoverflow.com/a/66127889
    # Posted by Vova, modified by community. See post 'Timeline' for change history
    # Retrieved 2025-11-25, License - CC BY-SA 4.0

    for key, value in list(dict_input.items()):
        if isinstance(value, dict):
            delete_none_from_dict(value)
        elif value is None:
            del dict_input[key]
        elif isinstance(value, list):
            for v_i in value:
                if isinstance(v_i, dict):
                    delete_none_from_dict(v_i)

    return dict_input


def add_levels_to_dict(
    levels: "Sequence[Level]", column_name: str, output_dict: dict
) -> dict:
    """
    Add serialized level descriptors under a column's ``Levels`` key.

    In BIDS sidecars, categorical columns can define a ``Levels`` mapping that
    explains the meaning of coded values. This helper converts a sequence of
    level-like dataclass instances into the required dictionary representation.

    Parameters
    ----------
    levels : Sequence[Level]
        Sequence of level objects, each expected to provide a ``level_name`` field and
        additional serializable metadata.
    column_name : str
        Name of the column entry inside ``output_dict`` that should receive the
        ``Levels`` mapping.
    output_dict : dict
        Dictionary to update in place.

    Returns
    -------
    dict
        Updated ``output_dict`` with a ``Levels`` entry under
        ``output_dict[column_name]``. When a level contains only a description, the
        stored value is that string; otherwise a nested metadata dictionary is stored.

    Raises
    ------
    KeyError
        Raised when ``column_name`` is not present in ``output_dict``.
    TypeError
        Raised when a level object cannot be converted with
        :py:func:`dataclasses.asdict`.

    See Also
    --------
    :py:func:`clean_dict`
        Cleans the serialized level metadata before insertion.

    Examples
    --------
    >>> from dataclasses import dataclass
    >>> @dataclass
    ... class Level:
    ...     level_name: str
    ...     description: str
    >>> output = {"trial_type": {}}
    >>> add_levels_to_dict([Level("go", "Go trial")], "trial_type", output)
    {'trial_type': {'Levels': {'go': 'Go trial'}}}
    """
    levels_dict = {}
    for level in levels:
        level_value = asdict(level)
        level_name = level_value.pop("level_name")
        level_value = clean_dict(
            level_value,
            skip_keys_to_manipulate=ManipulateKeysOption.ALL_KEYS_MANIPULATE,
        )
        if list(level_value.keys()) == ["description"]:
            level_value = level_value["description"]
        levels_dict[level_name] = level_value

    output_dict[column_name]["Levels"] = levels_dict
    return output_dict
