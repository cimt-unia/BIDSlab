"""
Typing protocols and aliases for base classes.

This module provides type variable definitions and protocol classes for the core
BIDS entity classes in BIDSlab. These type definitions enable static type checking,
enhance IDE support, and ensure type safety when working with polymorphic entities
throughout the codebase.
"""

#  Copyright (c) 2025 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

import os
from typing import TYPE_CHECKING, Protocol, TypeVar

if TYPE_CHECKING:
    from bidslab.common.base import BaseAcquisition, BaseTask, Entity
    from bidslab.common.specs_misc import Event, Run
    from bidslab.common.specs_summary import Scan


#: TypeVar bound to :py:class:`bidslab.common.base.BaseAcquisition` and its subclasses.
A = TypeVar("A", bound="BaseAcquisition")

#: TypeVar bound to :py:class:`bidslab.common.base.Entity` and its subclasses.
E = TypeVar("E", bound="Entity")

#: TypeVar bound to :py:class:`bidslab.common.specs_misc.Run` and its subclasses.
R = TypeVar("R", bound="Run")

#: TypeVar bound to :py:class:`bidslab.common.base.BaseTask` and its subclasses.
T = TypeVar("T", bound="BaseTask")

#: TypeVar bound to :py:class:`bidslab.common.specs_summary.Scan` and its subclasses.
SC = TypeVar("SC", bound="Scan")

#: TypeVar bound to :py:class:`bidslab.common.specs_misc.Event` and its subclasses.
EV = TypeVar("EV", bound="Event")


class Writable(Protocol):
    """
    Protocol for writable objects.

    A Writable is any object that can write itself to disk, therefore implements
    a :py:meth:`write` method. This protocol enables structural subtyping for
    objects that can be persisted to the filesystem.

    Notes
    -----
    This protocol is used throughout BIDSlab to ensure that entities can be
    written to disk. Any class that implements a :py:meth:`write` method with
    the correct signature automatically satisfies this protocol.
    """

    def write(self, output_path: os.PathLike | str) -> None:
        # numpydoc ignore=GL08
        ...


class PEntity(Writable, Protocol):
    """
    Protocol for Entity objects.

    A PEntity is any object that has an entity ID and name and is
    :py:class:`Writable`. This protocol combines the entity identifier attributes
    with the write capability, representing the minimal interface for BIDS entities.

    Attributes
    ----------
    _entity_id : str
        The unique identifier for the entity.
    _entity_name : str
        The name of the entity type.

    See Also
    --------
    Writable : Protocol
        Protocol for writable objects.
    :py:class:`bidslab.common.base.Entity`
        Base class for all entities in BIDSlab.

    Notes
    -----
    This protocol is used to define the common interface that all entity classes
    must implement. It enables type checking and IDE support for entity objects
    while allowing for structural subtyping.
    """

    _entity_id: str
    _entity_name: str
    _virtual_entity: bool
