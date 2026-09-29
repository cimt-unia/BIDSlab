"""
Motion extension models for BIDS motion-tracking datasets.

This module implements motion-specific task, tracking system, acquisition, run,
and channel classes together with helpers for reading and writing BIDS motion
sidecars and data tables.
"""

#  Copyright (c) 2025 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

import json
import os
import pathlib
import re
from collections.abc import Mapping, MutableSequence, Sequence
from dataclasses import asdict, dataclass
from typing import Any
from warnings import warn

import pandas as pd

from bidslab.common.base import BaseAcquisition, BaseTask, Entity, check_entity_mismatch
from bidslab.common.specs_misc import (
    Column,
    Event,
    Hardware,
    Institution,
    Run,
    get_events_from_files,
    write_events_to_files,
)
from bidslab.settings import get_settings_value
from bidslab.utils.dict_manipulation import (
    ManipulateKeysOption,
    clean_dict,
    delete_none_from_dict,
)
from bidslab.utils.exceptions import (
    FieldEntryNotValidError,
    TopLevelEntityNotLinkedWarning,
)
from bidslab.utils.helpers import (
    add_object_to_sequence,
    append_path,
    get_entity_from_file,
    get_tsv_json_files,
    load_tsv_data,
    parse_descriptive_tsv,
    parse_json_sidecar,
    set_attr_from_dict,
    write_entities,
    write_json,
)
from bidslab.utils.string_manipulation import to_snakecase

MOTION_CHANNEL_COMPONENT_ALLOWED_FIELD_ENTRIES = {
    "x",
    "y",
    "z",
    "quat_x",
    "quat_y",
    "quat_z",
    "quat_w",
    "n/a",
}

MOTION_CHANNEL_TYPE_ALLOWED_FIELD_ENTRIES = {
    "ACCEL",
    "ANGACCEL",
    "GYRO",
    "JNTANG",
    "LATENCY",
    "MAGN",
    "MISC",
    "ORNT",
    "POS",
    "VEL",
}


@dataclass(slots=True)
class ReferenceFrame:
    """
    Describe a named motion reference frame.

    Attributes
    ----------
    name : str
        Reference-frame label used in motion channel metadata, for example
        ``lab``, ``scanner``, ``head``, or ``segment-femur``.
    rotation_order : str | None, optional
        Axis order used when Euler rotations are stored, such as ``XYZ`` or
        ``ZYX``.
    rotation_rule : str | None, optional
        Convention describing intrinsic or extrinsic rotations, handedness, or
        another acquisition-specific rotation rule.
    spatial_axes : str | None, optional
        Human-readable description of axis directions, for example
        ``+X anterior, +Y left, +Z superior``.
    description : str | None, optional
        Free-text clarification of how the frame is defined in the laboratory or
        analysis workflow.

    See Also
    --------
    :py:class:`MotionChannel`
        Channel metadata that can reference the frame by object or name.
    :py:class:`TrackSys`
        Tracking-system container that owns acquisitions and their frame-aware
        channels.

    Notes
    -----
    Reference frame definitions are serialized under ``reference_frame`` levels
    in motion channel JSON sidecars. Use :py:class:`ReferenceFrame` instances on
    :py:class:`MotionChannel` objects when channel orientation depends on a
    laboratory, body-segment, or device-specific frame.

    Examples
    --------
    Create a laboratory frame with anatomical axis definitions:

    >>> frame = ReferenceFrame(
    ...     name="lab",
    ...     rotation_order="XYZ",
    ...     rotation_rule="intrinsic",
    ...     spatial_axes="+X anterior, +Y left, +Z superior",
    ...     description="Global optical motion-capture frame centered between" +
    ...         "force plates.",
    ... )

    Segment-local or device-local frames can be described in the same way:

    >>> pelvis = ReferenceFrame(
    ...     name="segment-pelvis",
    ...     spatial_axes="+X anterior, +Y left, +Z superior",
    ...     description="Pelvis frame derived from bilateral ASIS and PSIS markers.",
    ... )
    """

    name: str
    rotation_order: str | None = None
    rotation_rule: str | None = None
    spatial_axes: str | None = None
    description: str | None = None

    def __repr__(self) -> str:
        """Return a string representation of the ReferenceFrame object."""
        return f"<ReferenceFrame name={self.name}>"

    def __hash__(self) -> int:
        """Return a hash of the reference frame."""
        return id(self)


class MotionChannel:
    """
    Represent one channel in a BIDS motion recording.

    Parameters
    ----------
    name : str
        Channel name written to ``*_channels.tsv`` and used as a column label
        when :py:attr:`MotionRun.data` is loaded.
    component : str
        Motion component for the signal. Typical values include ``x``, ``y``,
        ``z`` for Cartesian measurements and ``quat_x`` ... ``quat_w`` for
        quaternion orientations.
    type : str
        BIDS motion channel type. Common examples are ``POS`` for marker
        position, ``ORNT`` for orientation, ``VEL`` for linear velocity,
        ``ACCEL`` for acceleration, and ``GYRO`` for angular velocity.
    tracked_point : str
        Name of the tracked marker, rigid body, joint, or segment associated
        with the channel, such as ``L_ankle`` or ``pelvis``.
    units : str
        Physical unit for the signal, for example ``mm``, ``m/s``,
        ``deg/s``, or ``rad``.
    **kwargs
        Optional channel metadata such as placement, status, reference frame,
        descriptive text, sidecar column definitions, and per-channel sampling
        overrides.

    Raises
    ------
    FieldEntryNotValidError
        If ``component`` or ``type`` is assigned a value outside the allowed BIDS
        vocabulary.

    See Also
    --------
    :py:class:`MotionRun`
        Container that groups channels with tabular sample data.
    :py:class:`ReferenceFrame`
        Optional frame metadata referenced by ``reference_frame``.

    Notes
    -----
    Combine ``type`` and ``component`` to express how a multiaxial signal is
    stored. For example, three ``POS`` channels with components ``x``, ``y``,
    and ``z`` can describe a tracked marker, while four ``ORNT`` channels with
    quaternion components can describe rigid-body orientation.

    Examples
    --------
    Define Cartesian position channels for a marker:

    >>> channels = [
    ...     MotionChannel("L_ankle_x", "x", "POS", "L_ankle", "mm"),
    ...     MotionChannel("L_ankle_y", "y", "POS", "L_ankle", "mm"),
    ...     MotionChannel("L_ankle_z", "z", "POS", "L_ankle", "mm"),
    ... ]

    Define quaternion orientation channels for a rigid body:

    >>> pelvis_frame = ReferenceFrame(name="segment-pelvis")
    >>> pelvis_qw = MotionChannel(
    ...     "pelvis_qw",
    ...     "quat_w",
    ...     "ORNT",
    ...     "pelvis",
    ...     "n/a",
    ...     reference_frame=pelvis_frame,
    ... )
    """

    def __init__(
        self,
        name: str,
        component: str,
        type: str,  # noqa: A002
        tracked_point: str,
        units: str,
        **kwargs: Any,
    ):
        self.name: str = name
        self._component: str = component
        self._type: str = type
        self.tracked_point: str = tracked_point
        self.units: str = units
        self.placement: str | None = None
        self.reference_frame: str | ReferenceFrame | None = None
        self.description: str | None = None
        self.sampling_frequency: int | float | None = None
        self.status: str | None = None
        self.status_description: str | None = None
        self.columns: MutableSequence[Column] | None = None

        set_attr_from_dict(self, kwargs)

    def __repr__(self) -> str:
        """Return a string representation of the MotionChannel object."""
        return f"<MotionChannel name={self.name}>"

    @property
    def type(self) -> str | None:
        # numpydoc ignore=RT01
        """Get the BIDS channel type."""
        return self._type

    @type.setter
    def type(self, value: str) -> None:
        # numpydoc ignore=GL08
        if value not in MOTION_CHANNEL_TYPE_ALLOWED_FIELD_ENTRIES:
            raise FieldEntryNotValidError(
                f"Field `Type` must be one "
                f"of {MOTION_CHANNEL_TYPE_ALLOWED_FIELD_ENTRIES}"
            )
        self._type = value

    @property
    def component(self) -> str | None:
        # numpydoc ignore=RT01
        """Get the channel component label."""
        return self._component

    @component.setter
    def component(self, value: str) -> None:
        # numpydoc ignore=GL08
        if value not in MOTION_CHANNEL_COMPONENT_ALLOWED_FIELD_ENTRIES:
            raise FieldEntryNotValidError(
                f"Field `Component` must be one "
                f"of {MOTION_CHANNEL_COMPONENT_ALLOWED_FIELD_ENTRIES}"
            )
        self._component = value


class MotionRun(Run):
    """
    Represent a motion run containing channels and tracked data.

    Parameters
    ----------
    base_path : os.PathLike | str
        Directory containing run-level motion files.
    run_id : int
        Numeric run identifier used to resolve ``run-<index>`` entities.
    virtual_entity : bool
        Parameter to distinguish virtual and real entities.
    **kwargs
        Optional linked objects and cached metadata, most commonly
        ``acquisition``, ``channels``, or preloaded ``data``.

    See Also
    --------
    :py:class:`MotionAcquisition`
        Parent acquisition that groups related runs.
    :py:class:`MotionChannel`
        Channel definitions used to label run data columns.

    Notes
    -----
    A :py:class:`MotionRun` lazily resolves its ``*_motion.tsv`` file when
    :py:attr:`data` is accessed. Channel names are applied after loading so the
    returned :py:class:`pandas.DataFrame` is ready for analysis.

    Examples
    --------
    Access channel metadata and motion samples:

    >>> run = acquisition.runs[0]
    >>> channel_table = run.list_channels()
    >>> samples = run.data

    Extract specific signals for downstream analysis:

    >>> ankle_xyz = samples[["L_ankle_x", "L_ankle_y", "L_ankle_z"]]
    >>> gyro_channels = [ch for ch in run.channels if ch.type == "GYRO"]
    """

    def __init__(
        self,
        base_path: os.PathLike | str,
        run_id: int,
        virtual_entity: bool = False,
        **kwargs: Any,
    ):
        super().__init__(
            base_path=base_path, run_id=run_id, virtual_entity=virtual_entity
        )

        self._channels: MutableSequence[MotionChannel] | None = None
        self._data: Any = None

        self._events: Sequence[Event] | None = None

        set_attr_from_dict(self, kwargs)

    @property
    def acquisition(self) -> "MotionAcquisition | None":
        # numpydoc ignore=RT01
        """Get the parent MotionAcquisition for this run."""
        if self._acquisition:
            return self._acquisition

        warn(
            "Run is not linked to a Acquisition object.", TopLevelEntityNotLinkedWarning
        )
        return self._acquisition

    @acquisition.setter
    def acquisition(self, value: "MotionAcquisition") -> None:
        # numpydoc ignore=GL08
        self._acquisition = value

    @property
    def channels(self) -> MutableSequence[MotionChannel] | None:
        # numpydoc ignore=RT01
        """Get the motion channels for this run."""
        return self._channels

    @channels.setter
    def channels(self, value: MutableSequence[MotionChannel]) -> None:
        # numpydoc ignore=GL08
        self._channels = value

    @property
    def data(self) -> pd.DataFrame:
        # numpydoc ignore=RT01
        """Load or return cached motion samples."""
        if self._data is None:
            file_name = ""

            # get list of top level entities
            entities = self.get_top_level_entities()

            # get all possible files with _motion.*
            files = list(self.root.glob("*_motion.*"))
            filenames = [f.name for f in files]
            file_entities = [f.split(".")[0].removesuffix("_motion") for f in filenames]

            # check for entity mismatches and use first one working
            for file in file_entities:
                # print(file, entities)
                if check_entity_mismatch(file, entities):
                    file_name = file

            tsv_path, _ = get_tsv_json_files(
                self.root,
                file_name + "_motion",
            )
            data_frame = load_tsv_data(path=tsv_path, header=None)
            column_names = {}
            for channel_number, channel in enumerate(self.channels):
                column_names[channel_number] = channel.name
            data_frame.rename(columns=column_names, inplace=True)

            self._data = data_frame

        return self._data

    @data.setter
    def data(self, value: pd.DataFrame) -> None:
        # numpydoc ignore=GL08
        self._data = value

    @property
    def events(self) -> Sequence[Event] | None:
        # numpydoc ignore=RT01
        """Load or return cached events sequence."""
        if self._events is None:
            self._events = get_events_from_files(self, self.root)

        return self._events

    @events.setter
    def events(self, value: Sequence[Event]) -> None:
        # numpydoc ignore=GL08
        self._events = value

    def list_channels(self) -> pd.DataFrame:
        """
        Return a channel table suitable for ``*_channels.tsv`` output.

        Returns
        -------
        pandas.DataFrame
            DataFrame with one row per motion channel, containing all channel
            metadata suitable for writing to a BIDS ``*_channels.tsv`` file.

        Notes
        -----
        The returned DataFrame excludes ``None`` values and internal attributes
        (such as ``columns``). Reference frame objects are replaced with their
        names for serialization.
        """
        channels_dataframe = pd.DataFrame()
        for motion_channel in self.channels if self.channels else []:
            channel_dict = motion_channel.__dict__.copy()
            channel_dict["component"] = channel_dict.pop("_component", None)
            channel_dict["type"] = channel_dict.pop("_type", None)

            channel_dict = delete_none_from_dict(channel_dict)

            reference_frame = channel_dict.pop("reference_frame", None)
            if isinstance(reference_frame, ReferenceFrame):
                channel_dict["reference_frame"] = reference_frame.name
            elif reference_frame:
                channel_dict["reference_frame"] = reference_frame

            channel_dict.pop("columns")
            # TODO: expand columns
            channels_dataframe = pd.concat(
                [channels_dataframe, pd.DataFrame([channel_dict])],
                ignore_index=True,
            )
        channels_dataframe.dropna(axis=1, how="all", inplace=True)
        return channels_dataframe

    def _reference_frames(self) -> set[ReferenceFrame]:
        """
        Collect unique :py:class:`ReferenceFrame` objects from channels.

        Returns
        -------
        set[ReferenceFrame]
            Set of unique reference frame objects referenced by this run's channels.

        Notes
        -----
        This is an internal helper method used for serializing reference frame
        metadata to channel JSON sidecars.
        """
        reference_frames_set = set()
        for motion_channel in self.channels if self.channels else []:
            reference_frame = motion_channel.reference_frame
            if isinstance(reference_frame, ReferenceFrame):
                reference_frames_set.add(reference_frame)
        return reference_frames_set

    def _columns(self) -> set[Column]:
        """
        Collect unique auxiliary channel columns for sidecar output.

        Returns
        -------
        set[Column]
            Set of unique :py:class:`Column` objects from this run's channels.

        Notes
        -----
        This is an internal helper method used for serializing column metadata
        to channel JSON sidecars.
        """
        columns_set = set()
        for motion_channel in self.channels if self.channels else []:
            for column in motion_channel.columns if motion_channel.columns else []:
                columns_set.add(column)
        return columns_set

    def write(self, output_path: os.PathLike | str) -> None:
        """
        Write motion data, channel tables, and channel sidecars.

        Parameters
        ----------
        output_path : os.PathLike or str
            Output file stem used to derive ``*_motion.tsv``, ``*_channels.tsv``,
            and ``*_channels.json`` files.

        Notes
        -----
        Writes three files:

        - ``*_motion.tsv``: Motion data samples
        - ``*_channels.tsv``: Channel metadata table
        - ``*_channels.json``: Channel sidecar with column descriptions and
            reference frame metadata
        """
        super().write(output_path)

        # write events files
        if self.events:
            write_events_to_files(self, self.events, output_path)

        output_path = pathlib.Path(output_path)
        # write motion data to "*_motion.tsv"
        output_path_data = append_path(output_path, "_motion.tsv")
        self.data.to_csv(output_path_data, sep="\t", index=False, header=False)

        # write channels description to "*_channels.tsv"
        output_path_channels = append_path(output_path, "_channels.tsv")
        channels_dataframe = self.list_channels()
        channels_dataframe.to_csv(output_path_channels, sep="\t", index=False)

        # write columns description to "*_channels.json"
        output_path_channel_description = append_path(output_path, "_channels.json")
        channel_description = {}

        columns = self._columns()
        for column in columns:
            column_dict = column.__dict__.copy()
            column_dict.pop("column_name")
            channel_description[column.column_name] = column_dict
        reference_frames = self._reference_frames()

        for reference_frame in reference_frames:
            reference_frame_dict = asdict(reference_frame)
            reference_frame_name = reference_frame_dict.pop("name")
            channel_description["reference_frame"]["Levels"] = {
                reference_frame_name: reference_frame_dict
            }

        channel_description = clean_dict(
            channel_description,
            skip_keys_to_manipulate=ManipulateKeysOption.SKIP_TOP_LEVEL_MANIPULATE,
        )
        write_json(channel_description, output_path_channel_description)


class MotionAcquisition(BaseAcquisition):
    """
    Represent a motion acquisition beneath a tracking system.

    Parameters
    ----------
    base_path : os.PathLike | str
        Directory containing acquisition-level motion files.
    acquisition_id : str
        BIDS acquisition label, usually written as ``acq-<label>``.
    sampling_frequency : int | float
        Nominal sampling frequency of the motion system in hertz.
    virtual_entity : bool
        Parameter to distinguish virtual and real entities.
    **kwargs
        Optional acquisition metadata such as channel counts, effective sampling
        frequency, missing-value markers, recording duration, and artifact
        descriptions.

    See Also
    --------
    :py:class:`TrackSys`
        Parent tracking-system entity.
    :py:class:`MotionRun`
        Run-level container for data and channels.

    Notes
    -----
    Acquisition metadata corresponds to motion JSON sidecar fields that apply
    across all runs within the same tracking system and acquisition label. Run
    discovery is file-based; if no explicit run entities are present, the class
    creates a default ``run-0`` object to preserve access to single-run datasets.

    Examples
    --------
    Create an acquisition from known metadata:

    >>> acquisition = MotionAcquisition(
    ...     base_path="sub-01/ses-01/motion",
    ...     acquisition_id="acq-walk",
    ...     sampling_frequency=120.0,
    ...     pos_channel_count=36,
    ...     tracked_points_count=12,
    ... )

    Iterate over discovered runs and access samples:

    >>> for run in acquisition.runs:
    ...     print(run.run_id, run.data.shape)
    """

    def __init__(
        self,
        base_path: os.PathLike | str,
        acquisition_id: str,
        sampling_frequency: int | float,
        virtual_entity: bool = False,
        **kwargs: Any,
    ):
        super().__init__(
            base_path=base_path,
            acquisition_id=acquisition_id,
            virtual_entity=virtual_entity,
        )

        self.sampling_frequency: int | float = sampling_frequency
        self.accel_channel_count: int | None = None
        self.angaccel_channel_count: int | None = None
        self.gyro_channel_count: int | None = None
        self.jntang_channel_count: int | None = None
        self.latency_channel_count: int | None = None
        self.magn_channel_count: int | None = None
        self.misc_channel_count: int | None = None
        self.missing_values: str | None = None
        self.motion_channel_count: int | None = None
        self.ornt_channel_count: int | None = None
        self.pos_channel_count: int | None = None
        self.sampling_frequency_effective: int | float | None = None
        self.subject_artefact_description: str | None = None
        self.tracked_points_count: int | float | None = None
        self.vel_channel_count: int | None = None

        # Recording duration belongs to run level --> !TODO: move to Run
        self._recording_duration: int | float | None = kwargs.pop(
            "RecordingDuration", None
        )

        # sampling_frequency_effective belongs to run level? --> !TODO: move to Run?
        self._sampling_frequency_effective: int | float | None = kwargs.pop(
            "SamplingFrequencyEffective", None
        )

        self._tracking_system: TrackSys | None = None

        set_attr_from_dict(self, kwargs)

    @property
    def tracking_system(self) -> "TrackSys | None":
        # numpydoc ignore=RT01
        """Get the parent tracking system linked to the acquisition."""
        if self._tracking_system:
            return self._tracking_system

        warn(
            "Acquisition is not linked to a TrackSys object.",
            TopLevelEntityNotLinkedWarning,
        )
        return self._tracking_system

    @tracking_system.setter
    def tracking_system(self, value: "TrackSys") -> None:
        # numpydoc ignore=GL08
        self._tracking_system = value

    @property
    def runs(self) -> dict[str, MotionRun]:
        # numpydoc ignore=RT01
        """Get runs contained in the acquisition."""
        if not self._runs:
            file_name = ""

            # get list of top level entities
            entities = self.get_top_level_entities()

            # get all possible files with _motion.*
            files_e = list(self.root.glob("*_channels.*"))
            filenames = [f.name for f in files_e]
            file_entities = [
                f.split(".")[0].removesuffix("_channels") for f in filenames
            ]

            # check for entity mismatches and use first one working
            for file in file_entities:
                if check_entity_mismatch(file, entities):
                    file_name = file

            tsv_path, json_path = get_tsv_json_files(
                self.root,
                file_name + "_channels",
            )
            channels = get_motion_channels(tsv_path=tsv_path, json_path=json_path)
            self._runs = {}
            files = self.root.iterdir()
            run_ids = set()
            for file in files:  # type: ignore [assignment]
                try:
                    run_ids.add(
                        get_entity_from_file(
                            file,  # type: ignore [arg-type]
                            "run",
                        )["run"]
                    )
                except KeyError:
                    continue
            for run_id in run_ids:
                self._runs.update(
                    {
                        run_id: MotionRun(
                            run_id=int(run_id),
                            base_path=self.root,
                            acquisition=self,
                            channels=channels,
                        )
                    }
                )

            # If no runs are found, add a default one
            if not self._runs:
                self._runs.update(
                    {
                        "run-0": MotionRun(
                            run_id=0,
                            base_path=self.root,
                            acquisition=self,
                            channels=channels,
                            virtual_entity=True,
                        )
                    }
                )

        return self._runs

    @runs.setter
    def runs(
        self, value: MutableSequence[int | MotionRun] | dict[str, MotionRun]
    ) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, MutableSequence):
            if all(isinstance(entry, int) for entry in value):
                self._runs = {}
                for entry in value:
                    assert isinstance(entry, int)  # for mypy
                    self._runs.update(
                        {
                            f"run-{entry}": MotionRun(
                                run_id=entry, base_path=self.root, acquisition=self
                            )
                        }
                    )
            elif all(isinstance(v, MotionRun) for v in value):
                self._runs = {}
                for entry in value:
                    assert isinstance(entry, MotionRun)  # for mypy
                    assert entry.run_id is not None
                    self._runs.update({entry.run_id: entry})
        elif isinstance(value, dict):
            self._runs = value
        else:
            raise TypeError("Field `Runs` must be a list of Run objects")

    def get_top_level_entities(self) -> list[str | Any]:
        """
        Method to get all top level entities.

        Returns
        -------
        list
            A list containing the entity_ids of all top level entities.
        """
        assert self.tracking_system is not None
        entities = self.tracking_system.get_top_level_entities()
        entities.append(self.acquisition_id)
        return entities


class TrackSys(Entity):
    """
    Represent a motion tracking system within a task.

    Parameters
    ----------
    base_path : os.PathLike | str
        Directory containing files for the tracking system.
    tracking_system_id : str
        BIDS tracking-system entity label, typically ``tracksys-<label>``.
    motion_description : dict | None, optional
        Parsed motion sidecar content inherited by acquisitions when explicit
        acquisition-level JSON sidecars are absent.
    virtual_entity : bool
        Parameter to distinguish virtual and real entities.
    **kwargs : dict | Hardware | Institution | MotionTask | MutableSequence
        Optional linked objects and metadata, including hardware, institution,
        parent task, and preconstructed acquisitions.

    See Also
    --------
    :py:class:`MotionTask`
        Task-level container that owns tracking systems.
    :py:class:`MotionAcquisition`
        Acquisition objects discovered under the tracking system.

    Notes
    -----
    Use :py:class:`TrackSys` to describe concrete motion-capture setups such as
    optical marker systems, inertial measurement units, depth-camera rigs, or
    magnetic trackers. The class preserves tracking-system-level metadata while
    exposing file-based acquisition discovery.

    Examples
    --------
    A task can contain multiple heterogeneous tracking systems:

    >>> optical = TrackSys(
    ...     base_path="sub-01/ses-01/motion",
    ...     tracking_system_id="tracksys-optical",
    ...     motion_description={"TrackingSystemName": "Vicon"},
    ... )
    >>> imu = TrackSys(
    ...     base_path="sub-01/ses-01/motion",
    ...     tracking_system_id="tracksys-imu",
    ...     motion_description={"TrackingSystemName": "Xsens"},
    ... )
    """

    def __init__(
        self,
        base_path: os.PathLike | str,
        tracking_system_id: str,
        motion_description: dict | None = None,
        virtual_entity: bool = False,
        **kwargs: "dict | Hardware | Institution | MotionTask | MutableSequence",
    ) -> None:
        super().__init__(
            _entity_id=tracking_system_id,
            _entity_name="tracksys",
            _virtual_entity=virtual_entity,
        )
        self._hardware: Hardware | None = None
        self._institution: Institution | None = None
        self._motion_description: dict = (
            motion_description if motion_description else {}
        )

        self.tracking_system_id: str = self._entity_id
        self.tracking_system_name: str | None = self._motion_description.pop(
            "TrackingSystemName", None
        )

        self.root: pathlib.Path = pathlib.Path(base_path)

        self._task: MotionTask | None = None

        self._acquisitions: dict[str, MotionAcquisition] | None = None

        set_attr_from_dict(self, kwargs)

    def __repr__(self) -> str:
        """Return a string representation of the TrackSys object."""
        return (
            f"<TrackSys id={self.tracking_system_id}, name={self.tracking_system_name}>"
        )

    @property
    def hardware(self) -> Hardware | None:
        # numpydoc ignore=RT01
        """Return hardware metadata linked to the tracking system."""
        return self._hardware

    @hardware.setter
    def hardware(self, value: dict | Hardware) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, dict):
            hardware_data = {}
            for k, v in value.items():
                hardware_data[to_snakecase(k)] = v
            self._hardware = Hardware(**hardware_data)
        elif isinstance(value, Hardware):
            self._hardware = value
        else:
            raise TypeError("Field `Hardware` must be a Hardware object")

    @property
    def institution(self) -> Institution | None:
        # numpydoc ignore=RT01
        """Return institution metadata linked to the tracking system."""
        return self._institution

    @institution.setter
    def institution(self, value: dict | Institution) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, dict):
            institution_data = {}
            for k, v in value.items():
                institution_data[to_snakecase(k)] = v
            self._institution = Institution(**institution_data)
        elif isinstance(value, Institution):
            self._institution = value
        else:
            raise TypeError("Field `Institution` must be a Institution object")

    @property
    def task(self) -> "MotionTask | None":
        # numpydoc ignore=RT01
        """Get the task linked to the tracking system."""
        if self._task:
            return self._task

        warn(
            "TrackSys is not linked to a Task object.",
            TopLevelEntityNotLinkedWarning,
        )
        return self._task

    @task.setter
    def task(self, value: "MotionTask") -> None:
        # numpydoc ignore=GL08
        self._task = value

    @property
    def acquisitions(self) -> dict[str, MotionAcquisition]:
        # numpydoc ignore=RT01
        """Get acquisitions associated with the tracking system."""
        if not self._acquisitions:
            self._acquisitions = {}
            files = self.root.iterdir()
            acquisition_ids = set()
            for file in files:
                try:
                    acquisition_ids.add(
                        get_entity_from_file(
                            file,
                            "acq",
                        )["acq"]
                    )
                except KeyError:
                    continue
            for acquisition_id in acquisition_ids:
                _, json_path = get_tsv_json_files(
                    self.root,
                    f"*{self.tracking_system_id}_acq-{acquisition_id}_*_motion",
                )

                if json_path:
                    data = parse_motion_json_sidecar(json_path)
                    acquisition_description = data["motion"]
                    sampling_frequency = acquisition_description.pop(
                        "SamplingFrequency"
                    )
                    self._acquisitions.update(
                        {
                            "acq-" + acquisition_id: MotionAcquisition(
                                base_path=self.root,
                                acquisition_id="acq-" + acquisition_id,
                                tracking_system=self,
                                sampling_frequency=sampling_frequency,
                                **acquisition_description,
                            )
                        }
                    )
                elif not get_settings_value("IGNORE_NOT_IMPLEMENTED"):
                    raise NotImplementedError  # TODO: implement

            # If no acquisitions are found, add a default one from
            # the motion description
            if not self._acquisitions:
                self._acquisitions.update(
                    {
                        "acq-00": MotionAcquisition(
                            acquisition_id="acq-00",
                            base_path=self.root,
                            tracking_system=self,
                            sampling_frequency=self._motion_description.pop(
                                "SamplingFrequency"
                            ),  # FIXME: dict entry can be None
                            virtual_entity=True,
                            **self._motion_description,
                        )
                    }
                )

        return self._acquisitions

    @acquisitions.setter
    def acquisitions(
        self,
        value: MutableSequence[Mapping | MotionAcquisition],
    ) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, MutableSequence):
            if all(isinstance(entry, Mapping) for entry in value):
                self._acquisitions = {}
                for entry in value:
                    assert isinstance(entry, Mapping)  # for mypy
                    self._acquisitions.update(
                        {
                            entry.acquisition_id: MotionAcquisition(  # type: ignore[attr-defined]
                                base_path=self.root, tracking_system=self, **entry
                            )
                        }
                    )
            elif all(isinstance(entry, MotionAcquisition) for entry in value):
                self._acquisitions = {}
                for entry in value:
                    assert isinstance(entry, MotionAcquisition)  # for mypy
                    assert entry.acquisition_id is not None
                    self._acquisitions.update({entry.acquisition_id: entry})
        else:
            raise TypeError(
                "Field `Acquisitions` must be a list or dict of Acquisition objects"
            )

    def get_top_level_entities(self) -> list[str | Any]:
        """
        Method to get all top level entities.

        Returns
        -------
        list
            A list containing the entity_ids of all top level entities.
        """
        assert self.task is not None
        entities = self.task.get_top_level_entities()
        entities.append(self.tracking_system_id)
        return entities

    def write(self, output_path: os.PathLike | str) -> None:
        """
        Write all acquisitions belonging to the tracking system.

        Parameters
        ----------
        output_path : os.PathLike or str
            Output path stem passed to nested acquisition writers.
        """
        write_entities(output_path, self.acquisitions.values())


class MotionTask(BaseTask):
    """
    Represent a BIDS motion task composed of tracking systems.

    Parameters
    ----------
    base_path : os.PathLike | str
        Root directory containing task-specific motion files.
    task_name : str
        BIDS task label used to resolve files such as ``task-<label>``.
    **kwargs : Any
        Optional inherited task metadata and linked tracking-system objects.

    See Also
    --------
    :py:class:`TrackSys`
        Tracking-system definitions contained in the task.
    :py:meth:`write`
        Serialize task, acquisition, and run metadata back to BIDS files.

    Notes
    -----
    Motion tasks often correspond to paradigms such as gait, reaching, balance,
    or calibration procedures. The :py:attr:`tracking_systems` property scans the
    task directory for ``tracksys`` entities and constructs :py:class:`TrackSys`
    objects from matching motion sidecars.

    Examples
    --------
    Load a motion task and inspect its hierarchy:

    >>> task = MotionTask(base_path="sub-01/ses-01/motion", task_name="walk")
    >>> for tracksys in task.tracking_systems:
    ...     print(tracksys.tracking_system_name, len(tracksys.acquisitions))

    Task-level access is convenient when the same paradigm mixes multiple motion
    modalities, such as optical tracking and wearable IMUs.
    """

    def __init__(
        self, base_path: os.PathLike | str, task_name: str, **kwargs: Any
    ) -> None:
        self._tracking_systems: dict[str, TrackSys] | None = None

        super().__init__(
            base_path=base_path, task_name=task_name, virtual_entity=False, **kwargs
        )

    @property
    def tracking_systems(self) -> dict[str, TrackSys]:
        # numpydoc ignore=RT01
        """Get tracking systems associated with the motion task."""
        if not self._tracking_systems:
            self._tracking_systems = {}
            files = list(self.root.glob(f"*_{self.task_id}_*"))
            tracking_systems_ids = set()
            for file in files:
                try:
                    tracking_systems_ids.add(
                        get_entity_from_file(
                            file,
                            "tracksys",
                        )["tracksys"]
                    )
                except KeyError:
                    continue
            for tracking_system_id in tracking_systems_ids:
                _, json_path = get_tsv_json_files(
                    self.root, f"*tracksys-{tracking_system_id}*_motion"
                )

                if json_path:
                    data = parse_motion_json_sidecar(json_path)
                    motion_description = data["motion"]  # FIXME: can be None
                    hardware_description = data["hardware"]  # FIXME: can be None
                    institution_description = data["institution"]  # FIXME: can be None
                    self._tracking_systems.update(
                        {
                            "tracksys-" + tracking_system_id: TrackSys(
                                tracking_system_id="tracksys-" + tracking_system_id,
                                base_path=self.root,
                                task=self,
                                hardware=hardware_description,
                                institution=institution_description,
                                motion_description=motion_description,
                            )
                        }
                    )
                elif not get_settings_value("IGNORE_NOT_IMPLEMENTED"):
                    raise NotImplementedError  # TODO: implement

            if not self._tracking_systems:
                pass
                # raise ..
                # TODO: If no tracking systems are found raise Error

        return self._tracking_systems

    @tracking_systems.setter
    def tracking_systems(self, value: MutableSequence[Mapping | TrackSys]) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, MutableSequence):
            if all(isinstance(entry, Mapping) for entry in value):
                self._tracking_systems = {}
                for entry in value:
                    assert isinstance(entry, Mapping)  # for mypy
                    self._tracking_systems.update(
                        {
                            entry.tracking_system_id: TrackSys(  # type: ignore[attr-defined]
                                base_path=self.root, task=self, **entry
                            )
                        }
                    )
            elif all(isinstance(entry, TrackSys) for entry in value):
                self._tracking_systems = {}
                for entry in value:
                    assert isinstance(entry, TrackSys)  # for mypy
                    assert entry.tracking_system_id is not None
                    self._tracking_systems.update({entry.tracking_system_id: entry})
        else:
            raise TypeError(
                "Field `TrackingSystems` must be a list of TrackSys objects"
            )

    def write(self, output_path: os.PathLike | str) -> None:
        """
        Write motion data, channel tables, and channel sidecars.

        Parameters
        ----------
        output_path : os.PathLike or str
            Output file stem used to derive ``_motion`` and ``_channels`` files.
        """
        # write json sidecar to "*_motion.json"
        task_dict = self.__dict__.copy()
        for tracking_system in self.tracking_systems.values():
            hardware_dict = (
                asdict(tracking_system.hardware) if tracking_system.hardware else {}
            )
            institution_dict = (
                asdict(tracking_system.institution)
                if tracking_system.institution
                else {}
            )
            output_path_tracksys = append_path(
                output_path, f"_{tracking_system.tracking_system_id}"
            )
            for acquisition in tracking_system.acquisitions.values():
                acquisition_dict = acquisition.__dict__.copy()
                output_path_acquisition = (
                    append_path(output_path_tracksys, f"_{acquisition.acquisition_id}")
                    if not acquisition._virtual_entity
                    else output_path_tracksys
                )
                for run in acquisition.runs.values():
                    run_dict = run.__dict__.copy()
                    output_path_run = (
                        append_path(output_path_acquisition, f"_{run.run_id}")
                        if not run._virtual_entity
                        else output_path_acquisition
                    )

                    motion_description = {
                        **task_dict,
                        **hardware_dict,
                        **institution_dict,
                        **acquisition_dict,
                        **run_dict,
                    }
                    motion_description.pop("acquisition_id")
                    motion_description.pop("run_id")
                    motion_description = clean_dict(
                        motion_description,
                        skip_keys_to_manipulate=ManipulateKeysOption.ALL_KEYS_MANIPULATE,
                    )
                    output_path_motion_description = append_path(
                        output_path_run, "_motion.json"
                    )
                    write_json(motion_description, output_path_motion_description)

        write_entities(output_path, self.tracking_systems.values())


def parse_motion_json_sidecar(sidecar_path: pathlib.Path) -> dict:
    """
    Split a motion JSON sidecar into task, hardware, institution, and motion blocks.

    Parameters
    ----------
    sidecar_path : pathlib.Path
        Path to the motion JSON sidecar.

    Returns
    -------
    dict
        Dictionary containing ``task``, ``hardware``, ``institution``, and
        ``motion`` sub-dictionaries.

    See Also
    --------
    :py:func:`parse_json_sidecar`
        Generic function for parsing JSON sidecar files.
    """
    with sidecar_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
        task_description = {}
        hardware_description = {}
        institution_description = {}
        motion_description = {}
        for key, value in data.items():
            if re.match(r"^Task[A-Z].*|^Instructions", key):
                task_description[key] = value
            elif re.match(r"^Device[A-Z].*|^Manufacturer.*|^Software[A-Z].*", key):
                hardware_description[key] = value
            elif re.match(r"^Institution.*", key):
                institution_description[key] = value
            else:
                motion_description[key] = value

        return {
            "task": task_description,
            "hardware": hardware_description,
            "institution": institution_description,
            "motion": motion_description,
        }


def get_reference_frames(reference_frames_levels: dict) -> dict[str, ReferenceFrame]:
    """
    Create :py:class:`ReferenceFrame` objects from sidecar ``Levels`` data.

    Parameters
    ----------
    reference_frames_levels : dict
        Dictionary containing reference frame metadata from a motion JSON sidecar,
        typically extracted from the ``Levels`` field under ``reference_frame``.

    Returns
    -------
    dict[str, ReferenceFrame]
        Dictionary mapping reference frame names to :py:class:`ReferenceFrame` objects.

    See Also
    --------
    :py:class:`ReferenceFrame`
        Dataclass representing a single motion reference frame.
    :py:func:`get_motion_channels`
        Function that uses reference frames to build motion channel objects.
    """
    reference_frames_dict = {}
    for ref_frame_name, ref_frame_values in reference_frames_levels.items():
        ref_frame_values_snakecase = {}
        for key, val in ref_frame_values.items():
            ref_frame_values_snakecase[to_snakecase(key)] = val
        reference_frames_dict[ref_frame_name] = ReferenceFrame(
            name=ref_frame_name, **ref_frame_values_snakecase
        )

    return reference_frames_dict


def get_motion_channels(
    tsv_path: pathlib.Path | None,
    json_path: pathlib.Path | None,
) -> MutableSequence[MotionChannel]:
    """
    Build motion channel objects from BIDS ``*_channels`` files.

    Parameters
    ----------
    tsv_path : pathlib.Path | None
        Path to a BIDS ``*_channels.tsv`` file containing motion channel definitions.
        If provided, channel data is parsed from the TSV file.
    json_path : pathlib.Path | None
        Path to a BIDS ``*_channels.json`` sidecar file containing channel metadata.
        If provided, column definitions and reference frame metadata are parsed
        from the JSON file.

    Returns
    -------
    MutableSequence[MotionChannel]
        List of :py:class:`MotionChannel` objects constructed from the parsed
        TSV and JSON metadata, with associated column and reference-frame information.

    See Also
    --------
    :py:class:`MotionChannel`
        Dataclass representing a single motion channel definition.
    :py:func:`get_reference_frames`
        Function used to build reference frame objects from JSON metadata.

    Notes
    -----
    If both ``tsv_path`` and ``json_path`` are provided, column metadata and
    reference frame definitions from the JSON file are used to enrich the
    channel definitions from the TSV file. Either or both parameters can be
    ``None``, resulting in an empty list.
    """
    motion_channels: list[MotionChannel] = []
    columns = []
    reference_frames_dict = None

    if json_path:
        column_data = parse_json_sidecar(json_path)

        reference_frames_data = column_data.pop("reference_frame", None)
        if isinstance(reference_frames_data, dict):
            reference_frames_levels = reference_frames_data.pop("Levels")
            reference_frames_dict = get_reference_frames(reference_frames_levels)

        columns.append(Column(name="reference_frame", **reference_frames_data))
        for column_name, column_values in column_data.items():
            columns.append(Column(name=column_name, **column_values))

    if tsv_path:
        data = parse_descriptive_tsv(tsv_path)
        for motion_channel in data:
            assert isinstance(motion_channel, dict), "Must be dicts in Generator."

            reference_frame_name = motion_channel.pop("reference_frame")
            if (
                reference_frames_dict is not None
                and reference_frame_name in reference_frames_dict
            ):
                reference_frame = reference_frames_dict[reference_frame_name]
            else:
                reference_frame = reference_frame_name
            add_object_to_sequence(
                entity_list=motion_channels,
                entity_class=MotionChannel,
                columns=columns,
                reference_frame=reference_frame,
                **motion_channel,
            )

    return motion_channels
