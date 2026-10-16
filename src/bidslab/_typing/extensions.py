"""
Typing protocols and aliases for extensions.

This module provides type variable definitions for BIDS extension-specific classes
in BIDSlab. These type definitions enable static type checking, enhance IDE support,
and ensure type safety when working with extension entities such as Motion and EMG.
"""

#  Copyright (c) 2026 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from bidslab.extensions.eeg import EEGChannel, EEGElectrode
    from bidslab.extensions.emg import EMGChannel, EMGElectrode
    from bidslab.extensions.ieeg import IEEGChannel, IEEGElectrode
    from bidslab.extensions.motion import MotionChannel

#: TypeVar bound to :py:class:`bidslab.extensions.motion.MotionChannel`
#: and its subclasses.
MC = TypeVar("MC", bound="MotionChannel")

#: TypeVar bound to :py:class:`bidslab.extensions.emg.EMGChannel` and its subclasses.
EC = TypeVar("EC", bound="EMGChannel")

#: TypeVar bound to :py:class:`bidslab.extensions.emg.EMGElectrode` and its subclasses.
EE = TypeVar("EE", bound="EMGElectrode")

#: TypeVar bound to :py:class:`bidslab.extensions.eeg.EEGChannel` and its subclasses.
EEC = TypeVar("EEC", bound="EEGChannel")

#: TypeVar bound to :py:class:`bidslab.extensions.eeg.EEGElectrode` and its subclasses.
EEE = TypeVar("EEE", bound="EEGElectrode")

#: TypeVar bound to :py:class:`bidslab.extensions.ieeg.IEEGChannel` and its subclasses.
IEEC = TypeVar("IEEC", bound="IEEGChannel")

#: TypeVar bound to :py:class:`bidslab.extensions.ieeg.IEEGElectrode`and its subclasses.
IEEE = TypeVar("IEEE", bound="IEEGElectrode")
