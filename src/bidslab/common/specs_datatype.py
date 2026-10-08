"""
Datatype entities in BIDSlab.

This module provides the Datatype class for managing BIDS datatype entities,
which represent different types of data acquisitions (e.g., MEG, EEG, motion)
within a session. It handles loading, parsing, and organizing tasks associated
with each datatype.
"""

#  Copyright (c) 2025 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

import os
import pathlib
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any
from warnings import warn

from bidslab.common.base import BaseTask
from bidslab.common.specs_task import Task
from bidslab.extensions.eeg import EEGTask, parse_eeg_json_sidecar
from bidslab.extensions.emg import EMGTask, parse_emg_json_sidecar
from bidslab.extensions.ieeg import IEEGTask, parse_ieeg_json_sidecar
from bidslab.extensions.motion import MotionTask, parse_motion_json_sidecar
from bidslab.settings import get_settings_value
from bidslab.utils.dict_manipulation import ManipulateKeysOption, clean_dict
from bidslab.utils.exceptions import TopLevelEntityNotLinkedWarning
from bidslab.utils.helpers import (
    get_entity_from_file,
    get_tsv_json_files,
    set_attr_from_dict,
    write_entities,
)
from bidslab.utils.string_manipulation import to_snakecase

if TYPE_CHECKING:
    from bidslab.common.specs_summary import Session

# Datatypes that can contain task information in BIDS
DATATYPES_WITH_TASKS = {
    # "anat",  # needs special implementation
    "meg",
    "eeg",
    "ieeg",
    "beh",
    "pet",
    "nirs",
    "motion",
    "emg",
}


class Datatype:
    """
    Represents a datatype entity in a BIDS dataset.

    A Datatype represents a specific type of data acquisition (e.g., MEG, EEG,
    motion capture) within a session. It manages the tasks and runs associated
    with that datatype and provides methods to access and manipulate them.

    Parameters
    ----------
    base_path : os.PathLike | str
        The file system path to the datatype directory.
    datatype_name : str
        The name of the datatype (e.g., "meg", "eeg", "motion").
    **kwargs : Session | Iterable
        Additional keyword arguments to set as attributes, including a Session
        object if linking to a parent session.

    Attributes
    ----------
    datatype_name : str
        The name of the datatype.
    root : pathlib.Path
        The file system path to the datatype directory.

    See Also
    --------
    Session : The parent session entity that contains datatypes.
    Task : Individual task entities within a datatype.

    Notes
    -----
    This class automatically discovers and loads tasks from the datatype
    directory based on the datatype name. Tasks are lazily loaded when accessed
    through the :py:attr:`tasks` property.
    """

    def __init__(
        self,
        base_path: os.PathLike | str,
        datatype_name: str,
        **kwargs: "Session | Iterable",
    ) -> None:
        self.datatype_name: str = datatype_name

        self.root: pathlib.Path = pathlib.Path(base_path)

        self._session: Session | None = None

        self._tasks: dict[str, BaseTask] | None = None

        if kwargs:
            set_attr_from_dict(self, kwargs)

    def __repr__(self) -> str:
        """Return a string representation of the Datatype object."""
        return f"<Datatype datatype_name={self.datatype_name}>"

    @property
    def session(self) -> "Session | None":
        # numpydoc ignore=RT01
        """Get the parent Session object for this Datatype."""
        if self._session:
            return self._session

        warn(
            "Datatype is not linked to a Session object.",
            TopLevelEntityNotLinkedWarning,
        )
        return self._session

    @session.setter
    def session(self, value: "Session") -> None:
        # numpydoc ignore=GL08
        self._session = value

    @property
    def tasks(self) -> dict[str, BaseTask]:
        # numpydoc ignore=RT01
        """Get the tasks associated with this Datatype."""
        if not self._tasks:
            self._tasks = {}
            if self.datatype_name in DATATYPES_WITH_TASKS:
                files = self.root.iterdir()
                task_ids = set()
                for file in files:
                    try:
                        task_ids.add(
                            get_entity_from_file(
                                file,
                                "task",
                            )["task"]
                        )
                    except KeyError:
                        continue
                create_tasks(self, task_ids)

            elif not get_settings_value("IGNORE_NOT_IMPLEMENTED"):
                raise NotImplementedError

            # If no tasks are found, create a default one
            if not self._tasks:
                self._tasks.update(
                    {
                        "task-00": Task(
                            task_name="n/a",
                            task_id="task-00",
                            base_path=self.root,
                            virtual_entity=True,
                            datatype=self,
                        )
                    }
                )

        return self._tasks

    @tasks.setter
    def tasks(self, value: Iterable[Mapping] | Iterable[BaseTask]) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, Iterable):
            if all(isinstance(entry, Mapping) for entry in value):
                self._tasks = {}
                for entry in value:
                    assert isinstance(entry, Mapping)  # for mypy
                    self._tasks.update(
                        {entry.task_id: Task(base_path=self.root, **entry)}  # type: ignore[attr-defined]
                    )
            elif all(isinstance(entry, BaseTask) for entry in value):
                self._tasks = {}
                for entry in value:
                    assert isinstance(entry, BaseTask)  # for mypy
                    assert entry.task_id is not None
                    self._tasks.update({entry.task_id: entry})
        else:
            raise TypeError("Field `Tasks` must be a list of Task objects")

    def get_top_level_entities(self) -> list[str | Any]:
        """
        Method to get all top level entities.

        Returns
        -------
        list
            A list containing the entity_ids of all top level entities.
        """
        assert self.session is not None
        return self.session.get_top_level_entities()

    def write(self, output_path: os.PathLike | str) -> None:
        """
        Write the datatype and its tasks to disk.

        Parameters
        ----------
        output_path : os.PathLike | str
            The file system path where the datatype directory should be written.

        Returns
        -------
        None
            Task-level files are written as side effects.

        See Also
        --------
        bidslab.utils.helpers.write_entities : Function for writing entities to disk.

        Notes
        -----
        The method delegates serialization to
        :py:func:`bidslab.utils.helpers.write_entities` so each task can emit
        modality-specific BIDS files beneath ``output_path``.

        Examples
        --------
        >>> datatype.write("out/sub-01_ses-01")
        """
        write_entities(output_path, self.tasks.values())


def create_tasks(cls: Datatype, task_ids: set[str]) -> None:
    """
    Create the tasks and add them to the cls object.

    Parameters
    ----------
    cls : Datatype
        The datatype object where the tasks should be added to.
    task_ids : set[str]
        Set of task ids found for the respective datatype.

    Returns
    -------
    None
        Tasks in the cls object are updated.
    """
    # create the task and update the tasks dict in the cls object

    for task_id in task_ids:
        _, json_path = get_tsv_json_files(
            cls.root, f"*task-{task_id}*_{cls.datatype_name}"
        )
        if not json_path:
            raise FileNotFoundError

        match cls.datatype_name:
            case "eeg":
                data = parse_eeg_json_sidecar(json_path)
                data_desc = clean_dict(
                    data,
                    skip_keys_to_manipulate=ManipulateKeysOption.ALL_KEYS_MANIPULATE,
                    string_manipulation=to_snakecase,
                )
                # TODO: add electrodes here like with emg
                task_description = data_desc.pop("task", None)
                task_name = task_description.pop("task_name", None)
                description = {
                    "_description": data_desc,
                    **task_description,
                }
                cls._tasks.update(
                    {
                        "task-" + task_id: EEGTask(
                            task_id="task-" + task_id,
                            task_name=task_name,
                            base_path=cls.root,
                            datatype=cls,
                            **description,
                        )
                    }
                )
            case "ieeg":
                data = parse_ieeg_json_sidecar(json_path)
                data_desc = clean_dict(
                    data,
                    skip_keys_to_manipulate=ManipulateKeysOption.ALL_KEYS_MANIPULATE,
                    string_manipulation=to_snakecase,
                )
                # TODO: add electrodes here like with emg
                task_description = data_desc.pop("task", None)
                task_name = task_description.pop("task_name", None)
                description = {
                    "_description": data_desc,
                    **task_description,
                }
                cls._tasks.update(
                    {
                        "task-" + task_id: IEEGTask(
                            task_id="task-" + task_id,
                            task_name=task_name,
                            base_path=cls.root,
                            datatype=cls,
                            **description,
                        )
                    }
                )
            case "emg":
                data = parse_emg_json_sidecar(json_path)
                data_desc = clean_dict(
                    data,
                    skip_keys_to_manipulate=ManipulateKeysOption.ALL_KEYS_MANIPULATE,
                    string_manipulation=to_snakecase,
                )
                # TODO: add electrodes here
                task_description = data_desc.pop("task", None)
                task_name = task_description.pop("task_name", None)
                description = {
                    "_description": data_desc,
                    **task_description,
                }
                cls._tasks.update(
                    {
                        "task-" + task_id: EMGTask(
                            task_id="task-" + task_id,
                            task_name=task_name,
                            base_path=cls.root,
                            datatype=cls,
                            **description,
                        )
                    }
                )
            case "motion":
                data = parse_motion_json_sidecar(json_path)
                task_name = data["task"].pop("TaskName")
                cls._tasks.update(
                    {
                        "task-" + task_id: MotionTask(
                            task_id="task-" + task_id,
                            task_name=task_name,
                            base_path=cls.root,
                            datatype=cls,
                            **data["task"],
                        )
                    }
                )
            case _:
                if not get_settings_value("IGNORE_NOT_IMPLEMENTED"):
                    raise NotImplementedError
