"""
Base classes for entities in BIDSlab.

This module provides abstract base classes for entities used in the BIDSlab
library. These base classes define common attributes and methods that all
entities must implement, ensuring a consistent interface across different
types of entities.
"""

#  Copyright (c) 2025 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

import os
import pathlib
from abc import ABC, abstractmethod
from collections.abc import MutableSequence, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic
from warnings import warn

from bidslab._typing import R
from bidslab.utils.exceptions import (
    FieldMissingError,
    TopLevelEntityNotLinkedWarning,
)
from bidslab.utils.helpers import (
    set_attr_from_dict,
    write_entities,
)
from bidslab.utils.string_manipulation import remove_special_characters

if TYPE_CHECKING:
    from bidslab.common.specs_datatype import Datatype


@dataclass
class Entity(ABC):
    """
    Abstract base class for all entities in BIDSlab.

    Attributes
    ----------
    _entity_id : str
        The unique identifier for the entity.
    _entity_name : str
        The name of the entity type.
    _virtual_entity : bool
        Parameter to distinguish virtual and real entities.

    Notes
    -----
    This class serves as a base for all entities in BIDSlab, providing common private
    attributes and an abstract method for writing the entity to disk.
    The :py:meth:`write` method must be implemented by all subclasses and serves as a
    Protocol for writing the entity's data to a specified output path.
    """

    _entity_id: str
    _entity_name: str
    _virtual_entity: bool

    @abstractmethod
    def write(self, output_path: os.PathLike | str) -> None:
        """
        Abstract method to write the entity to disk.

        Parameters
        ----------
        output_path : os.PathLike | str
            The path where the entity should be written.

        See Also
        --------
        bidslab.utils.helpers.write_entities
            Function for writing entities to disk.

        Notes
        -----
        This method must be implemented by all subclasses of Entity and serves as a
        Protocol for writing the entity's data to a specified output path.
        """
        ...

    # recursive method that returns all top level entities above this one
    @abstractmethod
    def get_top_level_entities(self) -> list[str | Any]:
        """
        Abstract method to get all top level entities.

        Returns
        -------
        list
            A list containing the entity_ids of all top level entities.
        """
        ...


def check_entity_mismatch(filename: str, entitylist: Sequence[str]) -> bool:
    """
    Check if the entity_ids in a filename match the ones in a list.

    Parameters
    ----------
    filename : str
        The part of filename containing the entities.
    entitylist : Sequence[str]
        A list with the entity_ids.

    Returns
    -------
    bool
        The matching of both inputs.
    """
    entities = filename.split("_")
    return set(entities).issubset(entitylist)


class BaseTask(Entity, ABC):
    """
    Abstract base class for Task entities in BIDSlab.

    This class implements a BaseTask entity not intended to be instantiated directly.
    It serves as a base for specific task implementations, providing common attributes
    and methods that all task entities must implement.

    Parameters
    ----------
    base_path : os.PathLike | str
        The base path where the task data is located.
    task_name : str
        The name of the task.
    virtual_entity : bool
        Parameter to distinguish virtual and real entities.
    **kwargs
        Additional keyword arguments to set as attributes of the task. Refer to the
        attributes for possible fields.

    Attributes
    ----------
    task_id : str | None
        The unique identifier for the task. Will be automatically generated from
        :py:attr:`task_name` if not provided.
    task_name : str
        The name of the task.
    task_description : str | None
        A description of the task.
    instructions : str | None
        Instructions for the task.
    root : pathlib.Path
        The root path of the task data.
    datatype : Datatype | None
        The top-level Datatype object linked to the Task.
    """

    @abstractmethod
    def __init__(
        self,
        base_path: os.PathLike | str,
        task_name: str,
        virtual_entity: bool = False,
        **kwargs: Any,
    ) -> None:
        self.task_id: str | None = None
        self.task_name: str = task_name  # !: This is required
        self.task_description: str | None = None
        self.instructions: str | None = None

        self.root: pathlib.Path = pathlib.Path(base_path)

        self._datatype: Datatype | None = None

        if kwargs:
            set_attr_from_dict(self, kwargs)

        if not self.task_name:
            raise FieldMissingError("Field `TaskName` is required in Task")

        if not self.task_id:
            self.task_id = f"task-{remove_special_characters(self.task_name)}"

        super().__init__(
            _entity_id=self.task_id, _entity_name="task", _virtual_entity=virtual_entity
        )

    def __repr__(self) -> str:
        """Return a string representation of the Task entity."""
        return f"<Task id={self.task_id}>"

    def get_top_level_entities(self) -> list[str | Any]:
        """
        Method to get all top level entities.

        Returns
        -------
        list
            A list containing the entity_ids of all top level entities.
        """
        assert self.datatype is not None
        entities = self.datatype.get_top_level_entities()
        entities.append(self.task_id)
        return entities

    @abstractmethod
    def write(self, output_path: os.PathLike | str) -> None:
        """
        Abstract method to write the entity to disk.

        Parameters
        ----------
        output_path : os.PathLike | str
            The path where the entity should be written.

        See Also
        --------
        bidslab.utils.helpers.write_entities
            Function for writing entities to disk.
        """
        pass

    @property
    def datatype(self) -> "Datatype | None":
        # numpydoc ignore=RT01
        """Property to get or set the top-level Datatype object."""
        if self._datatype:
            return self._datatype

        warn("Task is not linked to a Datatype object.", TopLevelEntityNotLinkedWarning)
        return self._datatype

    @datatype.setter
    def datatype(self, value: "Datatype") -> None:
        # numpydoc ignore=GL08
        self._datatype = value


class BaseAcquisition(Entity, Generic[R], ABC):  # noqa: UP046
    """
    Abstract base class for Acquisition entities in BIDSlab.

    This class implements a BaseAcquisition entity not intended to be instantiated
    directly. It serves as a base for specific acquisition implementations, providing
    common attributes and methods that all acquisition entities must implement.

    Parameters
    ----------
    base_path : os.PathLike | str
        The base path where the acquisition data is located.
    acquisition_id : str
        The unique identifier for the acquisition.
    virtual_entity : bool
        Parameter to distinguish virtual and real entities.

    Attributes
    ----------
    acquisition_id : str
        The unique identifier for the acquisition.
    root : pathlib.Path
        The root path of the acquisition data.
    runs : MutableSequence[R] | None
        The top-level Run objects associated with the Acquisition.
    """

    @abstractmethod
    def __init__(
        self,
        base_path: os.PathLike | str,
        acquisition_id: str,
        virtual_entity: bool = False,
    ) -> None:
        super().__init__(
            _entity_id=acquisition_id,
            _entity_name="acq",
            _virtual_entity=virtual_entity,
        )
        self.acquisition_id: str = self._entity_id  # !: This is required

        self.root: pathlib.Path = pathlib.Path(base_path)

        self._runs: dict[str, R] | None = None

    def __repr__(self) -> str:
        """Return a string representation of the Acquisition entity."""
        return f"<Acquisition id={self.acquisition_id}>"

    @property
    @abstractmethod
    def runs(self) -> dict[str, R]:
        """
        Abstract Property to get or set the top-level Run object.

        This property must be implemented by all subclasses of BaseAcquisition to
        manage the top-level :py:class:`~bidslab.specs_misc.Run` or its inherited
        objects associated with the Acquisition.
        """
        pass

    @runs.setter
    @abstractmethod
    def runs(self, value: MutableSequence[int | R] | dict[str, R]) -> None:
        # numpydoc ignore=GL08
        pass

    def write(self, output_path: os.PathLike | str) -> None:  # numpydoc ignore=PR01
        """
        Write the entity to disk.

        See Also
        --------
        bidslab.utils.helpers.write_entities
            Function for writing entities to disk.
        """
        write_entities(output_path, self.runs.values())
