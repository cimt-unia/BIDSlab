"""
Typing subpackage for BIDSlab.

This subpackage provides type definitions, type variables, and protocols used
throughout the BIDSlab package. It enables static type checking, improves IDE
support, and ensures type safety when working with BIDS entities.

The subpackage is organized into:

- :py:mod:`bidslab._typing.base` - Type definitions for core BIDS entity classes
- :py:mod:`bidslab._typing.extensions` - Type definitions for extension-specific
  classes

See Also
--------
:py:mod:`bidslab._typing.base`
    Type definitions for base classes including Acquisition, Entity, Run, and Task.
:py:mod:`bidslab._typing.extensions`
    Type definitions for extension classes including MotionChannel, EMGChannel,
    and EMGElectrode.

Notes
-----
This is an internal module primarily used for type hints within BIDSlab itself.
Users typically do not need to import from this module directly, as the types
are used internally by the library's functions and classes.
"""

#  Copyright (c) 2025 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

__all__ = [
    "EC",
    "EE",
    "EEC",
    "EEE",
    "EV",
    "IEEC",
    "IEEE",
    "MC",
    "SC",
    "A",
    "E",
    "PEntity",
    "R",
    "T",
    "Writable",
]

from .base import EV, SC, A, E, PEntity, R, T, Writable
from .extensions import EC, EE, EEC, EEE, IEEC, IEEE, MC
