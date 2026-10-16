"""
Task-level BIDS specification classes.

This module provides the generic :py:class:`Task` implementation used to model
BIDS task entities and discover acquisition sub-entities from an existing
dataset tree.
"""

#  Copyright (c) 2025 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

import os
from collections.abc import MutableSequence
from typing import TYPE_CHECKING

from bidslab.common.base import BaseTask
from bidslab.common.specs_misc import Acquisition
from bidslab.settings import get_settings_value
from bidslab.utils.helpers import get_entity_from_file

if TYPE_CHECKING:
    from bidslab.common.specs_datatype import Datatype


class Task(BaseTask):
    """
    Represent a generic BIDS task entity.

    Parameters
    ----------
    base_path : os.PathLike or str
        Directory containing files for the task.
    task_name : str
        Human-readable task name used to derive the BIDS ``task-`` entity.
    virtual_entity : bool
        Parameter to distinguish virtual and real entities.
    **kwargs
        Additional task metadata and optional linked entities.

    Attributes
    ----------
    cog_atlas_id : str | None
        Optional Cognitive Atlas identifier for specialized task modalities.
    cog_poid : str | None
        Optional Cognitive Paradigm Ontology identifier.
    acquisitions : MutableSequence[Acquisition]
        Acquisition objects associated with this task.

    See Also
    --------
    :py:class:`bidslab.common.base.BaseTask`
        Abstract base class providing common task behavior.
    :py:class:`bidslab.common.specs_misc.Acquisition`
        Acquisition entity loaded beneath a task.

    Notes
    -----
    The base implementation discovers acquisitions from filenames containing the
    ``acq-`` entity.
    """

    def __init__(
        self,
        base_path: os.PathLike | str,
        task_name: str,
        virtual_entity: bool = False,
        **kwargs: "str | Datatype | MutableSequence",
    ) -> None:
        self.cog_atlas_id = None  # !: Only for special datatypes
        self.cog_poid = None  # !: Only for special datatypes

        self._acquisitions: dict[str, Acquisition] | None = None

        super().__init__(
            base_path=base_path,
            task_name=task_name,
            virtual_entity=virtual_entity,
            **kwargs,
        )

    @property
    def acquisitions(self) -> dict[str, Acquisition]:
        # numpydoc ignore=RT01
        """Get acquisitions associated with the task."""
        if not self._acquisitions:
            self._acquisitions = {}
            files = self.root.iterdir()
            acquisition_labels = set()
            for file in files:
                try:
                    acquisition_labels.add(
                        get_entity_from_file(
                            file,
                            "acq",
                        )["acq"]
                    )
                except KeyError:
                    continue
            for acquisition_label in acquisition_labels:
                self._acquisitions.update(
                    {
                        "acq-" + acquisition_label: Acquisition(
                            acquisition_id="acq-" + acquisition_label,
                            base_path=self.root,
                        )
                    }
                )

            # If no acquisitions are found, add a default one
            if not self._acquisitions:
                self._acquisitions.update(
                    {
                        "acq-00": Acquisition(
                            acquisition_id="acq-00",
                            base_path=self.root,
                            virtual_entity=True,
                        )
                    }
                )

        return self._acquisitions

    @acquisitions.setter
    def acquisitions(
        self, value: MutableSequence[str | Acquisition] | dict[str, Acquisition]
    ) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, MutableSequence):
            if all(isinstance(entry, str) for entry in value):
                self._acquisitions = {}
                for entry in value:
                    assert isinstance(entry, str)  # for mypy
                    self._acquisitions.update(
                        {
                            entry: Acquisition(
                                acquisition_id=entry,
                                base_path=self.root,
                            )
                        }
                    )
            elif all(isinstance(v, Acquisition) for v in value):
                self._acquisitions = {}
                for entry in value:
                    assert isinstance(entry, Acquisition)  # for mypy
                    self._acquisitions.update({entry.acquisition_id: entry})
        elif isinstance(value, dict):
            self._acquisitions = value
        else:
            raise TypeError(
                "Field `Acquisitions` must be a list of Acquisition objects"
            )

    def write(self, output_path: os.PathLike | str) -> None:  # noqa: ARG002
        """
        Write task-level files to disk.

        Parameters
        ----------
        output_path : os.PathLike or str
            Destination directory for task content.

        Returns
        -------
        None
            This method is currently a placeholder.

        Raises
        ------
        NotImplementedError
            If generic task serialization is requested while
            ``IGNORE_NOT_IMPLEMENTED`` is disabled.

        Warnings
        --------
        This method is not yet implemented and will raise a NotImplementedError
        if the IGNORE_NOT_IMPLEMENTED setting is not enabled.

        Notes
        -----
        Generic task serialization has not yet been implemented in BIDSlab.
        Specialized task subclasses are expected to provide concrete writers.
        """
        # TODO: implement writing of basic Task data
        if not get_settings_value("IGNORE_NOT_IMPLEMENTED"):
            raise NotImplementedError
