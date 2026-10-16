"""
Phenotype and participant-measurement specification classes.

This module models phenotype columns and participant-linked measurement tools
used for BIDS ``phenotype/`` tables.
"""

#  Copyright (c) 2025 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any
from warnings import warn

from bidslab.common.specs_misc import Column
from bidslab.settings import get_settings_value
from bidslab.utils.checks import check_if_valid_uri
from bidslab.utils.exceptions import TopLevelEntityNotLinkedWarning

if TYPE_CHECKING:
    from bidslab.common.specs_summary import Participant


class PhenotypeColumn(Column):
    """
    Represent a column definition in a BIDS phenotype table.

    Parameters
    ----------
    name : str
        Column name as it appears in the TSV/JSON sidecar.
    **kwargs
        Additional :py:class:`~bidslab.common.specs_misc.Column` metadata plus
        the optional ``derivative`` flag.

    Attributes
    ----------
    derivative : bool | None
        Whether the phenotype column contains derived rather than directly
        observed data.

    Raises
    ------
    ValueError
        If ``derivative`` is neither boolean, ``None``, nor the strings
        ``"true"``/``"false"``.

    See Also
    --------
    :py:class:`MeasurementTool`
        Container for phenotype rows that may reference these columns.

    Notes
    -----
    BIDS phenotype JSON sidecars may extend regular column metadata with
    phenotype-specific annotations such as derivative status.
    """

    def __init__(
        self, name: str, **kwargs: bool | str | int | float | Mapping | Iterable
    ) -> None:
        derivative = kwargs.pop("derivative", None)
        match derivative:
            case bool() | None:
                pass
            case "true":
                derivative = True
            case "false":
                derivative = False
            case _:
                raise ValueError(
                    f"PhenotypeColumn 'derivative' field must be of type bool or None, "
                    f"got {type(derivative)}"
                )
        super().__init__(name=name, **kwargs)
        self.derivative: bool | None = derivative


class MeasurementTool:
    """
    Represent one phenotype measurement row for a participant.

    Parameters
    ----------
    name : str
        Measurement tool name, typically derived from the phenotype filename.
    **kwargs
        Additional row values and metadata such as ``description``,
        ``term_url``, ``columns``, and ``participant``.

    Attributes
    ----------
    name : str
        Measurement tool name.
    description : str | None
        Human-readable description of the tool.
    term_url : str | None
        URI referencing a controlled vocabulary term for the tool.
    columns : Sequence[PhenotypeColumn] | None
        Column metadata for rows emitted by the measurement tool.
    participant : Participant | None
        Participant linked through the :py:attr:`participant` property.

    Raises
    ------
    ValueError
        If ``term_url`` is invalid and validation overrides are disabled.

    See Also
    --------
    :py:class:`PhenotypeColumn`
        Column metadata used by phenotype measurement tables.

    Notes
    -----
    Instances are often created from rows in ``phenotype/<tool>.tsv`` and then
    attached to :py:class:`~bidslab.common.specs_summary.Participant` objects.
    """

    def __init__(self, name: str, **kwargs: Any) -> None:
        self.name: str = name
        self.description: str | None = None
        self.term_url: str | None = None

        self._participant: Participant | None = None

        self.columns: Sequence[PhenotypeColumn] | None = None

        for key, value in kwargs.items():
            setattr(self, key, value)

        if self.term_url and not get_settings_value("OVERRIDE_VALIDATION"):  # type: ignore[unreachable]
            check_if_valid_uri(self.term_url)  # type: ignore[unreachable]

    def __repr__(self) -> str:
        """Return a string representation of the MeasurementTool object."""
        return f"<MeasurementTool name={self.name}>"

    @property
    def participant(self) -> "Participant | None":
        # numpydoc ignore=RT01
        """Get the participant linked to this measurement."""
        if self._participant:
            return self._participant

        warn("Participant is not linked to a Dataset", TopLevelEntityNotLinkedWarning)
        return self._participant

    @participant.setter
    def participant(self, value: "Participant") -> None:
        # numpydoc ignore=GL08
        self._participant = value
