"""
EMG extension models for BIDS electromyography datasets.

This module implements EMG-specific hardware, coordinate system, channel,
electrode, recording, acquisition, and task models together with helper
functions for parsing EMG sidecars and tabular metadata.
"""

#  Copyright (c) 2026 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

import json
import os
import pathlib
import re
from collections.abc import Mapping, MutableMapping, MutableSequence, Sequence
from dataclasses import asdict, dataclass
from typing import (
    TYPE_CHECKING,
    Any,
)
from warnings import warn

import pandas as pd

from bidslab.common.base import BaseAcquisition, BaseTask, check_entity_mismatch
from bidslab.common.specs_misc import (
    Column,
    Event,
    Filter,
    Hardware,
    Institution,
    Recording,
    Run,
    get_events_from_files,
    write_events_to_files,
)
from bidslab.utils.dict_manipulation import ManipulateKeysOption, clean_dict
from bidslab.utils.exceptions import (
    FieldEntryNotValidError,
    FieldMissingError,
    FileNotFoundWarning,
    TopLevelEntityNotLinkedWarning,
)
from bidslab.utils.helpers import (
    add_object_to_sequence,
    append_path,
    copy_file,
    get_edf_json_files,
    get_entity_from_file,
    get_tsv_json_files,
    load_edf_data,
    parse_descriptive_tsv,
    parse_json_sidecar,
    set_attr_from_dict,
    write_entities,
    write_json,
)
from bidslab.utils.string_manipulation import to_snakecase

if TYPE_CHECKING:
    from bidslab.common import Datatype

EMG_CHANNEL_TYPE_ALLOWED_FIELD_ENTRIES = {
    "ECG",
    "EMG",
    "EOG",
    "HEOG",
    "LATENCY",
    "MISC",
    "REF",
    "SYSCLOCK",
    "TRIG",
    "VEOG",
}


@dataclass(slots=True)
class EMGHardware(Hardware):
    """
    Extend generic hardware metadata with EMG electrode manufacturer fields.

    Attributes
    ----------
    electrode_manufacturer : str | None, optional
        Manufacturer of the surface, fine-wire, or high-density electrodes used
        during acquisition.
    electrode_manufacturers_model_name : str | None, optional
        Manufacturer-reported model name or catalog number for the electrodes.

    See Also
    --------
    :py:class:`EMGRecording`
        Recording-level container that links hardware and channel metadata.

    Notes
    -----
    Store electrode-specific vendor information here when the amplifier and the
    electrodes come from different manufacturers. This complements the inherited
    :py:class:`~bidslab.common.specs_misc.Hardware` fields describing the main
    recording system.

    Examples
    --------
    Record both amplifier and electrode vendor information

    >>> hardware = EMGHardware(
    ...     manufacturer="Delsys",
    ...     manufacturers_model_name="Trigno Avanti",
    ...     electrode_manufacturer="Delsys",
    ...     electrode_manufacturers_model_name="DE-2.1",
    ... )
    """

    electrode_manufacturer: str | None = None
    electrode_manufacturers_model_name: str | None = None


@dataclass(slots=True)
class EMGCoordinateSystem:
    """
    Represent an EMG electrode coordinate system.

    Attributes
    ----------
    name : str
        Local identifier used to reference the coordinate system.
    emg_coordinate_system : str
        Coordinate-system keyword defined by the BIDS standard, for example
        ``CapTrak``, ``EEGLAB`` or ``Other``.
    emg_coordinate_units : str
        Spatial units used for electrode coordinates, typically ``mm`` or ``cm``.
    emg_coordinate_system_description : str | None, optional
        Required explanatory text when ``emg_coordinate_system`` is ``Other``.
    parent_coordinate_system : EMGCoordinateSystem | None, optional
        Parent system used for hierarchical localization, such as registering a
        muscle grid to a body-segment frame.
    anchor_coordinates : Sequence[int | float] | None, optional
        Coordinates of the anchor point in the parent system.
    anchor_electrode : str | None, optional
        Electrode name used as anchor when nesting coordinate systems.

    Raises
    ------
    FieldMissingError
        If a required description or anchoring field is omitted.

    See Also
    --------
    :py:class:`EMGElectrode`
        Electrode definitions that use this coordinate system.
    :py:class:`EMGRecording`
        Recording-level container that aggregates electrodes and channels.

    Notes
    -----
    The EMG extension requires additional descriptive fields when the coordinate
    system is ``Other`` or linked to a parent coordinate system. This is useful
    for documenting electrode grids on anatomical landmarks, custom templates,
    or digitized skin coordinates.

    Examples
    --------
    Define a digitized anatomical coordinate system

    >>> coords = EMGCoordinateSystem(
    ...     name="forearm-grid",
    ...     emg_coordinate_system="Other",
    ...     emg_coordinate_units="mm",
    ...     emg_coordinate_system_description=(
    ...         "2D grid aligned with the radius-ulna axis on the dominant forearm."
    ...     ),
    ... )

    Register a child grid to a segment-level parent frame

    >>> EMGCoordinateSystem(
    ...     name="biceps-grid",
    ...     emg_coordinate_system="Other",
    ...     emg_coordinate_units="mm",
    ...     emg_coordinate_system_description="High-density grid placed over biceps " +
    ...         "brachii.",
    ...     parent_coordinate_system=coords,
    ...     anchor_coordinates=[25, 10, 0],
    ...     anchor_electrode="E01",
    ... )
    """

    name: str
    emg_coordinate_system: str
    emg_coordinate_units: str
    emg_coordinate_system_description: str | None = None
    parent_coordinate_system: str | None = None
    anchor_coordinates: Sequence[int | float] | None = None
    anchor_electrode: str | None = None

    def __post_init__(self):
        """Validate coordinate system configuration."""
        if (
            self.emg_coordinate_system == "Other"
            and not self.emg_coordinate_system_description
        ):
            raise FieldMissingError(
                "Field `EMGCoordinateSystemDescription` must be present if field "
                "`EMGCoordinateSystem` is 'Other'"
            )
        if self.parent_coordinate_system:
            if not self.anchor_coordinates:
                raise FieldMissingError(
                    "Field `AnchorCoordinates` must be present if field "
                    "`ParentCoordinateSystem` is present"
                )
            if not self.anchor_electrode:
                raise FieldMissingError(
                    "Field `AnchorElectrode` must be present if field "
                    "`ParentCoordinateSystem` is present"
                )

    def __repr__(self) -> str:
        """Return a string representation of the EMGCoordinateSystem object."""
        return f"<EMGCoordinateSystem name={self.name}>"

    def __hash__(self) -> int:
        """Return a hash of the coordinate system."""
        return id(self)


class EMGChannel:
    """
    Represent one EMG channel definition from ``*_channels.tsv``.

    Parameters
    ----------
    name : str
        Channel name used in tabular metadata and renamed sample data columns.
    type : str
        BIDS channel type. Typical values are ``EMG`` for muscle activity,
        ``REF`` for reference leads, ``TRIG`` for trigger inputs, ``ECG`` or
        ``EOG`` for physiological monitoring, and ``MISC`` for auxiliary signals.
    units : str
        Measurement unit such as ``uV``, ``mV``, or ``V``.
    **kwargs
        Optional metadata describing electrode pairing, target muscle, filters,
        channel grouping, placement scheme, and status information.

    Raises
    ------
    FieldEntryNotValidError
        If ``type`` is not allowed by the EMG extension.

    See Also
    --------
    :py:class:`EMGRecording`
        Recording object that owns channel definitions and sample data.
    :py:class:`EMGElectrode`
        Electrode definitions referenced by ``signal_electrode`` or ``reference``.

    Notes
    -----
    Use channel metadata to document whether a signal comes from a bipolar pair,
    monopolar sensor, reference channel, or synchronization input. Placement and
    muscle annotations help downstream processing pipelines organize channels.

    Examples
    --------
    Create a bipolar muscle channel and a trigger channel

    >>> emg = EMGChannel(
    ...     name="EMG_FCR",
    ...     type="EMG",
    ...     units="uV",
    ...     target_muscle="flexor carpi radialis",
    ...     signal_electrode="E01",
    ...     reference="E02",
    ... )
    >>> trig = EMGChannel(name="Trigger", type="TRIG", units="V")
    """

    def __init__(
        self,
        name: str,
        type: str,  # noqa: A002
        units: str,
        **kwargs: Any,
    ):
        self.name: str = name
        self._type: str = type
        self.units: str = units
        self.description: str | None = None
        self.sampling_frequency: int | float | None = None
        self.signal_electrode: str | None = None
        self.reference: str | None = None
        self.group: str | int | float | None = None
        self.target_muscle: str | None = None
        self.placement_scheme: str | None = None
        self.placement_description: str | None = None
        self.interelectrode_distance: int | float | None = None
        self.low_cutoff: int | float | None = None
        self.high_cutoff: int | float | None = None
        self.notch: str | None = None
        self.status: str | None = None
        self.status_description: str | None = None
        self.columns: Sequence[Column] | None = None

        set_attr_from_dict(self, kwargs)

    def __repr__(self) -> str:
        """Return a string representation of the EMGChannel object."""
        return f"<EMGChannel name={self.name}>"

    @property
    def type(self) -> str | None:
        # numpydoc ignore=RT01
        """Return the validated EMG channel type."""
        return self._type

    @type.setter
    def type(self, value: str) -> None:
        # numpydoc ignore=GL08
        if value not in EMG_CHANNEL_TYPE_ALLOWED_FIELD_ENTRIES:
            raise FieldEntryNotValidError(
                f"Field `Type` must be one of {EMG_CHANNEL_TYPE_ALLOWED_FIELD_ENTRIES}"
            )
        self._type = value


class EMGElectrode:
    """
    Represent one EMG electrode definition from ``*_electrodes.tsv``.

    Parameters
    ----------
    name : str
        Electrode label used in electrode tables and channel references.
    x : int | float
        X coordinate of the electrode center in the associated coordinate system.
    y : int | float
        Y coordinate of the electrode center in the associated coordinate system.
    **kwargs
        Optional metadata including ``z`` coordinates, electrode type, material,
        impedance, grouping, and linked :py:class:`EMGCoordinateSystem`.

    See Also
    --------
    :py:class:`EMGCoordinateSystem`
        Coordinate system used for electrode localization.
    :py:class:`EMGChannel`
        Channel metadata that can reference the electrode by name.

    Notes
    -----
    Use electrodes to document sensor placement on the skin, in a grid, or in a
    fine-wire configuration. Coordinate and impedance metadata are especially
    important for reproducible placement descriptions and quality control.

    Examples
    --------
    Describe a surface electrode

    >>> electrode = EMGElectrode(
    ...     name="E01",
    ...     x=12.5,
    ...     y=31.0,
    ...     z=0.0,
    ...     type="surface",
    ...     material="Ag/AgCl",
    ...     impedance=4.2,
    ... )
    """

    def __init__(
        self,
        name: str,
        x: int | float,
        y: int | float,
        **kwargs: Any,
    ):
        self.name: str = name
        self.x: int | float = x
        self.y: int | float = y
        self.z: int | float | None = None
        self.coordinate_system: EMGCoordinateSystem | None = None
        self.type: str | None = None
        self.material: str | None = None
        self.impedance: int | float | None = None
        self.group: str | int | float | None = None
        self.columns: Sequence[Column] | None = None

        set_attr_from_dict(self, kwargs)

    def __repr__(self) -> str:
        """Return a string representation of the EMGElectrode object."""
        return f"<EMGElectrode name={self.name}>"


class EMGRecording(Recording):
    """
    Represent one EMG recording and its associated metadata/data.

    Parameters
    ----------
    base_path : os.PathLike | str
        Directory containing the recording files.
    recording_id : str
        BIDS recording label, usually ``recording-<label>``.
    sampling_frequency : int | float
        Sampling rate of the recording in hertz.
    emg_placement_scheme : str
        Placement scheme identifier, for example ``SENIAM`` or ``Other``.
    emg_reference : str
        Description of the reference strategy, such as a dedicated reference
        electrode, common average, or differential pair.
    power_line_frequency : int | float | str
        Mains frequency affecting the recording, typically ``50`` or ``60``.
    recording_type : str
        Recording mode, such as continuous or epoched acquisition.
    software_filters : MutableMapping[str, Filter] | str
        Software filtering description stored in the EMG sidecar.
    virtual_entity : bool
        Parameter to distinguish virtual and real entities.
    **kwargs
        Optional recording metadata, linked hardware or institution objects,
        channels, electrodes, coordinate systems, and inherited sidecar content.

    Raises
    ------
    TypeError
        If ``_description`` is supplied with the wrong type.
    FieldMissingError
        If ``emg_placement_scheme`` is ``Other`` without an accompanying
        description.

    See Also
    --------
    :py:class:`EMGRun`
        Parent run containing one or more recordings.
    :py:class:`EMGChannel`
        Channel metadata used to label data columns.
    :py:class:`EMGElectrode`
        Electrode metadata associated with the recording.

    Notes
    -----
    :py:class:`EMGRecording` combines setup metadata with lazily loaded sample
    data. Use it to document electrode placement scheme, referencing, filtering,
    and recording-specific quality annotations before accessing :py:attr:`data`.

    Examples
    --------
    Create a recording with standard setup metadata

    >>> recording = EMGRecording(
    ...     base_path="sub-01/ses-01/emg",
    ...     recording_id="recording-rest",
    ...     sampling_frequency=2000,
    ...     emg_placement_scheme="SENIAM",
    ...     emg_reference="Bipolar differential",
    ...     power_line_frequency=50,
    ...     recording_type="continuous",
    ...     software_filters="None",
    ... )

    Access metadata and sample data together

    >>> muscles = [channel.target_muscle for channel in recording.channels or []]
    >>> samples = recording.data
    """

    def __init__(
        self,
        base_path: os.PathLike | str,
        recording_id: str,
        sampling_frequency: int | float,
        emg_placement_scheme: str,
        emg_reference: str,
        power_line_frequency: int | float | str,
        recording_type: str,
        software_filters: MutableMapping[str, Filter] | str,
        virtual_entity: bool = False,
        **kwargs: Any,
    ):
        # TODO: filters should be filter objects
        description = kwargs.pop("_description", None)
        if description is not None and not isinstance(description, MutableMapping):
            raise TypeError(
                "Parameter type for argument `_description` must be MutableMapping"
            )
        self._description: MutableMapping | None = description

        super().__init__(
            base_path=base_path,
            recording_id=recording_id,
            sampling_frequency=sampling_frequency,
            virtual_entity=virtual_entity,
        )

        self.emg_placement_scheme: str = emg_placement_scheme
        if self.emg_placement_scheme != "Other":
            self.emg_placement_scheme_description: str | None = None
        else:
            try:
                self.emg_placement_scheme_description = kwargs.pop(
                    "emg_placement_scheme_description"
                )
            except KeyError:
                raise FieldMissingError(
                    "Field `EMGPlacementSchemeDescription` must be present if field "
                    "`EMGPlacementScheme` is 'Other'"
                ) from None
        self.emg_reference: str = emg_reference
        self.power_line_frequency: int | float | str = power_line_frequency
        self.recording_type: str = recording_type
        self.software_filters: MutableMapping[str, Filter] | str = software_filters
        self.emg_channel_count: int | None = None
        self.hardware_filters: MutableMapping[str, Filter] | str | None = None
        self.recording_duration: int | float | None = None
        self.electrode_material: str | None = None
        self.electrode_type: str | None = None
        self.emg_ground: str | None = None
        self.epoch_length: int | float | None = None
        self.gain: int | float | None = None
        self.interelectrode_distance: int | float | None = None
        self.preamplification: int | float | None = None
        self.skin_preparation: str | None = None
        self.subject_artefact_description: str | None = None
        self.trigger_channel_count: int | None = None

        self._hardware: EMGHardware | None = None
        self._institution: Institution | None = None

        self._electrodes: MutableSequence[EMGElectrode] | None = None
        self._channels: MutableSequence[EMGChannel] | None = None
        self._coordinate_systems: MutableSequence[EMGCoordinateSystem] | None = None

        self._events: Sequence[Event] | None = None

        self._run: EMGRun | None = None

        # Try to set attributes from arguments
        set_attr_from_dict(self, kwargs)

        self._update_description()

        # Update values from self._description
        if self._description:
            emg_description = self._description.pop("emg", {})
            _ = self._description.pop("task", None)
            set_attr_from_dict(self, {**self._description, **emg_description})

    def __repr__(self) -> str:
        """Return a string representation of the EMGRecording entity."""
        return f"<EMGRecording id={self.recording_id}>"

    @property
    def hardware(self) -> EMGHardware | None:
        # numpydoc ignore=RT01
        """Return hardware metadata linked to the EMG recording."""
        return self._hardware

    @hardware.setter
    def hardware(self, value: Mapping | EMGHardware) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, Mapping):
            hardware_data = {}
            for k, v in value.items():
                hardware_data[to_snakecase(k)] = v
            self._hardware = EMGHardware(**hardware_data)
        elif isinstance(value, EMGHardware):
            self._hardware = value
        else:
            raise TypeError("Field `Hardware` must be an EMGHardware object")

    @property
    def institution(self) -> Institution | None:
        # numpydoc ignore=RT01
        """Return institution metadata linked to the EMG recording."""
        return self._institution

    @institution.setter
    def institution(self, value: Mapping | Institution) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, Mapping):
            institution_data = {}
            for k, v in value.items():
                institution_data[to_snakecase(k)] = v
            self._institution = Institution(**institution_data)
        elif isinstance(value, Institution):
            self._institution = value
        else:
            raise TypeError("Field `Institution` must be an Institution object")

    @property
    def channels(self) -> MutableSequence[EMGChannel] | None:
        # numpydoc ignore=RT01
        """Return channel definitions associated with the recording."""
        return self._channels

    @channels.setter
    def channels(self, value: MutableSequence[Mapping | EMGChannel]) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, MutableSequence):
            if all(isinstance(entry, Mapping) for entry in value):
                self._channels = []
                for entry in value:
                    assert isinstance(entry, Mapping)  # for mypy
                    self._channels.append(EMGChannel(**entry))
            elif all(isinstance(entry, EMGChannel) for entry in value):
                self._channels = value  # type: ignore[assignment]  # mypy cannot type narrow on all()
        else:
            raise TypeError("Field `Channels` must be a list of EMGChannel object")

    @property
    def electrodes(self) -> MutableSequence[EMGElectrode] | None:
        # numpydoc ignore=RT01
        """Return electrode definitions associated with the recording."""
        return self._electrodes

    @electrodes.setter
    def electrodes(self, value: MutableSequence[Mapping | EMGElectrode]) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, MutableSequence):
            if all(isinstance(entry, Mapping) for entry in value):
                self._electrodes = []
                for entry in value:
                    assert isinstance(entry, Mapping)  # for mypy
                    self._electrodes.append(EMGElectrode(**entry))
            elif all(isinstance(e, EMGElectrode) for e in value):
                self._electrodes = value  # type: ignore[assignment]  # mypy cannot type narrow on all()
        else:
            raise TypeError("Field `Electrodes` must be a list of EMGElectrodes object")

    @property
    def coordinate_systems(self) -> MutableSequence[EMGCoordinateSystem] | None:
        # numpydoc ignore=RT01
        """Return coordinate systems associated with the recording."""
        if self._coordinate_systems is None:
            self._coordinate_systems = []
            # TODO load corrdsystems from files
            entities = self.get_top_level_entities()

            # get all possible files with _coordsystem.json
            files_json = list(self.root.glob("*_coordsystem.json"))
            filenames_json = [f.name for f in files_json]
            file_entities_json = [
                f.removesuffix("_coordsystem.json") for f in filenames_json
            ]

            # check for entity mismatches and use first one working
            for file in file_entities_json:
                file_nospace = re.sub(r"_space.*$", "", file)
                if check_entity_mismatch(file_nospace, entities):
                    # load .json file and save it
                    data = parse_json_sidecar(self.root / (file + "_coordsystem.json"))
                    data = clean_dict(data, string_manipulation=to_snakecase)
                    # get the name (space-<name>) from the filename
                    nameparts = file.split("_")
                    name_dict = {
                        namepart.split("-")[0]: namepart.split("-")[1]
                        for namepart in nameparts
                    }
                    name = name_dict.pop("space", "")
                    self._coordinate_systems.append(
                        EMGCoordinateSystem(
                            name=name,
                            emg_coordinate_system=data.pop("emg_coordinate_system"),
                            emg_coordinate_units=data.pop("emg_coordinate_units"),
                            **data,
                        )
                    )

        return self._coordinate_systems

    @coordinate_systems.setter
    def coordinate_systems(self, value: MutableSequence[EMGCoordinateSystem]) -> None:
        # numpydoc ignore=GL08
        self._coordinate_systems = value

    @property
    def data(self) -> pd.DataFrame:
        # numpydoc ignore=RT01
        """Load or return cached EMG sample data."""
        if self._data is None:
            file_name = f"*{self.run.acquisition.task.task_id}*"
            file_name += (
                f"_{self.run.acquisition.acquisition_id}"
                if not self.run.acquisition._virtual_entity
                else ""
            )
            file_name += f"_{self.run.run_id}" if not self.run._virtual_entity else ""
            file_name += f"_{self.recording_id}" if not self._virtual_entity else ""
            edf_path, _ = get_edf_json_files(
                self.root,
                file_name + "_emg",
            )
            data_frame = load_edf_data(path=edf_path)
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

    def _update_description(self) -> None:
        """Update inherited description metadata for the recording."""
        file_name = f"*_{self.recording_id}_"
        _update_description_data(self, file_name)

    def write(self, output_path: str | os.PathLike) -> None:
        """
        Write recording-level EMG files.

        Parameters
        ----------
        output_path : os.PathLike | str
            The path where the output files will be written.
        """
        # write events files
        if self.events:
            write_events_to_files(self, self.events, output_path)

        # TODO write data files (_emg.bdf/edf/+)
        # assumes data is .edf
        # output_path_emg_data = append_path(output_path, "_emg.edf")

        # write json sidecar (_emg.json)
        output_path_emg_json = append_path(output_path, "_emg.json")
        emg_description = self.__dict__.copy()
        emg_description.pop("electrodes", None)
        emg_description.pop("channels", None)
        emg_description.pop("coordinate_systems", None)
        emg_description.pop("events", None)
        emg_description.pop("run", None)

        # emg_software_filters = emg_description.pop("software_filters", None)
        # emg_hardware_filters = emg_description.pop("hardware_filters", None)

        emg_hardware = emg_description.pop("_hardware", None)
        if emg_hardware is not None:
            emg_description.update(asdict(self._hardware))

        emg_institution = emg_description.pop("_institution", None)
        if emg_institution is not None:
            emg_description.update(asdict(self._institution))

        # add task information to eeg_description
        task_description = self.run.acquisition.task.__dict__.copy()
        task_description.pop("acquisitions", None)
        task_description.pop("_description", None)
        task_description.pop("task_id", None)
        task_description.pop("root", None)
        task_description.pop(
            "_acquisitions", None
        )  # idk why it is not removed by clean_dict
        emg_description.update(task_description)

        emg_description = clean_dict(emg_description)
        write_json(emg_description, output_path_emg_json)

        # write channels files (_channels.json, _channels.tsv)
        if self.channels:
            output_path_channels_json = append_path(output_path, "_channels.json")
            output_path_channels_tsv = append_path(output_path, "_channels.tsv")

            channels_dataframe = self.list_channels()
            channels_dataframe.to_csv(output_path_channels_tsv, sep="\t", index=False)

            # write channels description (.json)
            channel_description = {}

            columns = self.channels[0].columns
            for column in columns:
                column_dict = column.__dict__.copy()
                column_dict.pop("column_name")
                channel_description[column.column_name] = column_dict

            channel_description = clean_dict(
                channel_description,
                skip_keys_to_manipulate=ManipulateKeysOption.SKIP_TOP_LEVEL_MANIPULATE,
            )
            write_json(channel_description, output_path_channels_json)

        #  write electrodes files (_electrodes.tsv, _electrodes.json)
        if self.electrodes:
            output_path_electrodes_json = append_path(output_path, "_electrodes.json")
            output_path_electrodes_tsv = append_path(output_path, "_electrodes.tsv")

            electrodes_dataframe = self.list_electrodes()
            electrodes_dataframe.to_csv(
                output_path_electrodes_tsv, sep="\t", index=False
            )

            # write electrodes description (.json)
            electrode_description = {}

            columns = self.electrodes[0].columns
            for column in columns:
                column_dict = column.__dict__.copy()
                column_dict.pop("column_name")
                electrode_description[column.column_name] = column_dict

            electrode_description = clean_dict(
                electrode_description,
                skip_keys_to_manipulate=ManipulateKeysOption.SKIP_TOP_LEVEL_MANIPULATE,
            )
            write_json(electrode_description, output_path_electrodes_json)

        # write coordinate system files (_coordsystem.json)
        # path may contain space entity before recoring
        if self.coordinate_systems:
            for coordsystem in self.coordinate_systems:
                # build correct output path (order of entities)
                if coordsystem.name != "":
                    if self._virtual_entity:
                        output_path_coordsystem = append_path(
                            output_path, f"_space-{coordsystem.name}_coordsystem.json"
                        )
                    else:
                        filename = output_path.name
                        filename.split("_")
                        filename.append(filename[-1])
                        filename[-1] = f"space-{coordsystem.name}"
                        name = ""
                        name = (name + "_" + part for part in filename)
                        name = name + "_coordsystem.json"
                        output_path_coordsystem = append_path(output_path.parent, name)
                else:
                    output_path_coordsystem = append_path(
                        output_path, "_coordsystem.json"
                    )

                coord_dict = asdict(coordsystem)
                _ = coord_dict.pop("name", None)
                coord_dict = clean_dict(coord_dict)
                write_json(coord_dict, output_path=output_path_coordsystem)

        # write photo files if available (_photo.jpg/png/tif)
        photo_files = self.root.glob("*_photo.*")
        for photo in photo_files:
            copy_file(
                source_path=photo,
                destination_path=output_path.parent,
            )

    def list_channels(self) -> pd.DataFrame:
        """
        Return a channel table suitable for ``*_channels.tsv`` output.

        Returns
        -------
        pandas.DataFrame
            DataFrame with one row per emg channel, containing all channel
            metadata suitable for writing to a BIDS ``*_channels.tsv`` file.

        Notes
        -----
        The returned DataFrame excludes ``None`` values and internal attributes
        (such as ``columns``). Reference frame objects are replaced with their
        names for serialization.
        """
        channels_dataframe = pd.DataFrame()
        for emg_channel in self.channels if self.channels else []:
            channel_dict = emg_channel.__dict__.copy()
            channel_dict["component"] = channel_dict.pop("_component", None)
            channel_dict["type"] = channel_dict.pop("_type", None)

            coordinate_system = channel_dict.pop("coordinate_system", None)
            if isinstance(coordinate_system, EMGCoordinateSystem):
                channel_dict["coordinate_system"] = coordinate_system.name
            elif coordinate_system:
                channel_dict["coordinate_system"] = coordinate_system

            channel_dict.pop("columns")

            channel_dict = clean_dict(channel_dict)
            channels_dataframe = pd.concat(
                [channels_dataframe, pd.DataFrame([channel_dict])],
                ignore_index=True,
            )
        channels_dataframe.dropna(axis=1, how="all", inplace=True)
        return channels_dataframe

    def list_electrodes(self) -> pd.DataFrame:
        """
        Return a electrodes table suitable for ``*_electrodes.tsv`` output.

        Returns
        -------
        pandas.DataFrame
            DataFrame with one row per electrode, containing all electrode
            metadata suitable for writing to a BIDS ``*_electrodes.tsv`` file.

        Notes
        -----
        The returned DataFrame excludes ``None`` values and internal attributes
        (such as ``columns``). Reference frame objects are replaced with their
        names for serialization.
        """
        electrodes_dataframe = pd.DataFrame()
        for emg_electrode in self.electrodes if self.electrodes else []:
            electrode_dict = emg_electrode.__dict__.copy()

            coordinate_system = electrode_dict.pop("coordinate_system", None)
            if isinstance(coordinate_system, EMGCoordinateSystem):
                electrode_dict["coordinate_system"] = coordinate_system.name

            electrode_dict.pop("columns")

            electrode_dict = clean_dict(electrode_dict)
            electrodes_dataframe = pd.concat(
                [electrodes_dataframe, pd.DataFrame([electrode_dict])],
                ignore_index=True,
            )
        electrodes_dataframe.dropna(axis=1, how="all", inplace=True)
        return electrodes_dataframe


class EMGRun(Run):
    """
    Represent an EMG run containing one or more recordings.

    Parameters
    ----------
    base_path : os.PathLike | str
        Directory containing run-level EMG files.
    run_id : int
        Numeric run identifier used to resolve ``run-<index>`` entities.
    virtual_entity : bool
        Parameter to distinguish virtual and real entities.
    **kwargs : Any
        Optional acquisition link and inherited description metadata.

    Raises
    ------
    TypeError
        If ``_description`` is not a mutable mapping.

    See Also
    --------
    :py:class:`EMGAcquisition`
        Parent acquisition that groups runs.
    :py:class:`EMGRecording`
        Recording objects exposed through :py:attr:`recordings`.

    Notes
    -----
    Runs group one or more :py:class:`EMGRecording` objects. Recordings are
    discovered from filenames, and a default ``recording-00`` object is created
    when files omit the recording entity.

    Examples
    --------
    Access recordings and inspect loaded signals

    >>> run = acquisition.runs[0]
    >>> first_recording = run.recordings[0]
    >>> data = first_recording.data

    Iterate over all recording labels discovered in the run

    >>> for recording in run.recordings:
    ...     print(recording.recording_id, len(recording.channels or []))
    """

    def __init__(
        self,
        base_path: os.PathLike | str,
        run_id: int,
        virtual_entity: bool = False,
        **kwargs: Any,
    ):
        description = kwargs.pop("_description", {})
        if not isinstance(description, MutableMapping):
            raise TypeError(
                "Parameter type for argument `_description` must be MutableMapping"
            )
        self._description: MutableMapping = description

        super().__init__(
            base_path=base_path, run_id=run_id, virtual_entity=virtual_entity, **kwargs
        )

        self._recordings: dict[str, EMGRecording] | None = None

        self._update_description()

    # def __repr__(self) -> str:
    #     return f"<Run id=run-{self.run_id}>"

    @property
    def recordings(self) -> dict[str, EMGRecording] | None:
        # numpydoc ignore=RT01
        """Get recordings belonging to the run."""
        if not self._recordings:
            # TODO make this more elegant
            assert self.acquisition is not None
            file_name = f"*{self.acquisition.task.task_id}"
            file_name += (
                f"_{self.acquisition.acquisition_id}"
                if not self.acquisition._virtual_entity
                else ""
            )
            file_name += f"_{self.run_id}" if not self._virtual_entity else ""

            self._recordings = {}
            files = self.root.glob("*_emg.*")
            recording_labels = set()
            for file in files:
                try:
                    recording_labels.add(
                        get_entity_from_file(
                            file,
                            "recording",
                        )["recording"]
                    )
                except KeyError:
                    continue

            # values in self._description get passed forward as fallback / to follow the
            # inheritance principle of BIDS but will be updated downstream
            for recording_label in recording_labels:
                self._recordings.update(
                    {
                        "recording-" + recording_label: EMGRecording(
                            recording_id="recording-" + recording_label,
                            base_path=self.root,
                            run=self,
                            hardware=self._description.get("hardware", None),
                            institution=self._description.get("institution", None),
                            channels=get_emg_channels(
                                *get_tsv_json_files(
                                    self.root,
                                    file_name
                                    + f"_recording-{recording_label}_channels",
                                )
                            ),
                            electrodes=self._description.get("electrodes", None),
                            **self._description.get("emg", None),
                        )
                    }
                )

            # If no recordings are found, add a default one
            if not self._recordings:
                self._recordings.update(
                    {
                        "recording-00": EMGRecording(
                            recording_id="recording-00",
                            base_path=self.root,
                            run=self,
                            hardware=self._description.get("hardware", None),
                            institution=self._description.get("institution", None),
                            channels=get_emg_channels(
                                *get_tsv_json_files(
                                    self.root,
                                    file_name + "_channels",
                                )
                            ),
                            electrodes=self._description.get("electrodes", None),
                            virtual_entity=True,
                            **self._description.get("emg", None),
                        )
                    }
                )

        return self._recordings

    @recordings.setter
    def recordings(self, value: MutableSequence[MutableMapping | EMGRecording]) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, MutableSequence):
            if all(isinstance(entry, MutableMapping) for entry in value):
                self._recordings = {}
                for entry in value:
                    assert isinstance(entry, MutableMapping)  # for mypy
                    assert isinstance(entry["recording_id"], str)
                    self._recordings.update(
                        {
                            entry["recording_id"]: EMGRecording(
                                base_path=self.root,
                                run=self,
                                **entry,
                            )
                        }
                    )
            elif all(isinstance(entry, EMGRecording) for entry in value):
                self._recordings = {}
                for entry in value:
                    assert isinstance(entry, EMGRecording)
                    assert isinstance(entry.recording_id, str)
                    self._recordings.update({entry.recording_id: entry})
        else:
            raise TypeError(
                "Field `Recordings` must be a list of EMGRecordings objects"
            )

    def _update_description(self) -> None:
        """Refresh inherited description metadata for the run."""
        file_name = f"*_{self.run_id}_*"
        _update_description_data(self, file_name)

    def write(self, output_path: os.PathLike | str) -> None:
        """
        Write run-level EMG files.

        Parameters
        ----------
        output_path : os.PathLike | str
            The path where the output files will be written.
        """
        super().write(output_path)
        assert self.recordings is not None
        write_entities(output_path, self.recordings.values())
        # TODO what needs to be done with self.description?


class EMGAcquisition(BaseAcquisition):
    """
    Represent an EMG acquisition beneath a task.

    Parameters
    ----------
    base_path : os.PathLike | str
        Directory containing acquisition-level EMG files.
    acquisition_id : str
        BIDS acquisition label, usually ``acq-<label>``.
    task : EMGTask
        Top level task entity.
    virtual_entity : bool
        Parameter to distinguish virtual and real entities.
    **kwargs : Any
        Optional task link, inherited sidecar description metadata, and
        preconstructed runs.

    Raises
    ------
    TypeError
        If ``_description`` is not a mutable mapping.

    See Also
    --------
    :py:class:`EMGTask`
        Parent task containing the acquisition.
    :py:class:`EMGRun`
        Run objects created under the acquisition.

    Notes
    -----
    The acquisition acts as the bridge between task-level metadata and run-level
    recordings. It refreshes inherited description blocks and lazily constructs
    :py:class:`EMGRun` objects from files in the acquisition directory.

    Examples
    --------
    Create or load an acquisition and enumerate runs

    >>> acquisition = EMGAcquisition(
    ...     base_path="sub-01/ses-01/emg",
    ...     acquisition_id="acq-grip",
    ... )
    >>> run_ids = [run.run_id for run in acquisition.runs]
    """

    def __init__(
        self,
        base_path: os.PathLike | str,
        acquisition_id: str,
        task: "EMGTask",
        virtual_entity: bool = False,
        **kwargs: Any,
    ):
        description = kwargs.pop("_description", {})
        if not isinstance(description, MutableMapping):
            raise TypeError(
                "Parameter type for argument `_description` must be MutableMapping"
            )
        self._description: MutableMapping = description

        super().__init__(
            base_path=base_path,
            acquisition_id=acquisition_id,
            virtual_entity=virtual_entity,
        )

        self._task: EMGTask | None = task

        self._update_description()

        set_attr_from_dict(self, kwargs)

    @property
    def runs(self) -> dict[str, EMGRun]:
        # numpydoc ignore=RT01
        """Return runs associated with the acquisition."""
        if not self._runs:
            self._runs = {}
            files = self.root.iterdir()
            run_ids = set()
            for file in files:
                try:
                    run_ids.add(
                        get_entity_from_file(
                            file,
                            "run",
                        )["run"]
                    )
                except KeyError:
                    continue
            for run_id in run_ids:
                self._runs.update(
                    {
                        "run-" + run_id: EMGRun(
                            run_id=int(run_id),
                            base_path=self.root,
                            acquisition=self,
                            _description=self._description,
                        )
                    }
                )

            # If no runs are found, add a default one
            if not self._runs:
                self._runs.update(
                    {
                        "run-0": EMGRun(
                            run_id=0,
                            base_path=self.root,
                            acquisition=self,
                            _description=self._description,
                            virtual_entity=True,
                        )
                    }
                )

        return self._runs

    @runs.setter
    def runs(self, value: MutableSequence[int | EMGRun] | dict[str, EMGRun]) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, MutableSequence):
            if all(isinstance(entry, int) for entry in value):
                self._runs = {}
                for entry in value:
                    assert isinstance(entry, int)  # for mypy
                    self._runs.update(
                        {
                            f"run-{entry}": EMGRun(
                                run_id=entry,
                                base_path=self.root,
                                acquisition=self,
                                _description=self._description,
                            )
                        }
                    )
            elif all(isinstance(v, EMGRun) for v in value):
                self._runs = {}
                for v in value:
                    assert isinstance(v, EMGRun)
                    assert isinstance(v.run_id, str)
                    self._runs.update({v.run_id: v})
        elif isinstance(value, dict):
            self._runs = value
        else:
            raise TypeError("Field `Runs` must be a list of EMGRun objects")

    @property
    def task(self) -> "EMGTask | None":
        # numpydoc ignore=RT01
        """Get the parent :py:class:`EMGTask` linked to the acquisition."""
        if self._task:
            return self._task

        warn(
            "Acquisition is not linked to a EMGTask object.",
            TopLevelEntityNotLinkedWarning,
        )
        return self._task

    @task.setter
    def task(self, value: "EMGTask") -> None:
        # numpydoc ignore=GL08
        self._task = value

    def _update_description(self) -> None:
        """Refresh inherited description metadata for the acquisition."""
        file_name = f"*_{self.acquisition_id}_*_"
        if self._virtual_entity:
            assert self.task is not None
            file_name = f"*_{self.task.task_id}_*"
        else:
            file_name = f"*_{self.acquisition_id}_*"
        _update_description_data(self, file_name)

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
        entities.append(self.acquisition_id)
        return entities


class EMGTask(BaseTask):
    """
    Represent a BIDS EMG task composed of acquisitions.

    Parameters
    ----------
    base_path : os.PathLike | str
        Root directory containing task-specific EMG files.
    task_name : str
        BIDS task label used to resolve files such as ``task-<label>``.
    **kwargs : str | Datatype | MutableSequence | MutableMapping
        Optional task metadata, datatype information, inherited description
        blocks, and acquisition objects.

    Raises
    ------
    TypeError
        If ``_description`` is not a mutable mapping.

    See Also
    --------
    :py:class:`EMGAcquisition`
        Acquisition objects belonging to the task.
    :py:meth:`write`
        Task-level write entry point for future EMG serialization support.

    Notes
    -----
    EMG tasks typically describe paradigms such as rest, maximal voluntary
    contraction, gait, or grasping. The :py:attr:`acquisitions` property scans
    for acquisition entities and creates :py:class:`EMGAcquisition` objects with
    inherited metadata for downstream run and recording discovery.

    Examples
    --------
    Load an EMG task and inspect its hierarchy

    >>> task = EMGTask(base_path="sub-01/ses-01/emg", task_name="grip")
    >>> for acquisition in task.acquisitions:
    ...     print(acquisition.acquisition_id, len(acquisition.runs))
    """

    def __init__(
        self,
        base_path: os.PathLike | str,
        task_name: str,
        **kwargs: "str | Datatype | MutableSequence | MutableMapping",
    ) -> None:
        description = kwargs.pop("_description", {})
        if not isinstance(description, MutableMapping):
            raise TypeError(
                "Parameter type for argument `_description` must be MutableMapping"
            )
        self._description: MutableMapping = description

        super().__init__(
            base_path=base_path, task_name=task_name, virtual_entity=False, **kwargs
        )

        self._acquisitions: dict[str, EMGAcquisition] | None = None

    @property
    def acquisitions(self) -> dict[str, EMGAcquisition]:
        # numpydoc ignore=RT01
        """Return acquisitions discovered for the EMG task."""
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
                        "acq-" + acquisition_label: EMGAcquisition(
                            acquisition_id="acq-" + acquisition_label,
                            base_path=self.root,
                            task=self,
                            _description=self._description,
                        )
                    }
                )

            # If no acquisitions are found, add a default one
            if not self._acquisitions:
                self._acquisitions.update(
                    {
                        "acq-00": EMGAcquisition(
                            acquisition_id="acq-00",
                            base_path=self.root,
                            task=self,
                            _description=self._description,
                            virtual_entity=True,
                        )
                    }
                )

        return self._acquisitions

    @acquisitions.setter
    def acquisitions(
        self, value: MutableSequence[str] | MutableSequence[EMGAcquisition]
    ) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, MutableSequence):
            if all(isinstance(entry, str) for entry in value):
                self._acquisitions = {}
                for entry in value:
                    assert isinstance(entry, str)  # for mypy
                    self._acquisitions.update(
                        {
                            entry: EMGAcquisition(
                                acquisition_id=entry,
                                base_path=self.root,
                                task=self,
                                _description=self._description,
                            )
                        }
                    )
            elif all(isinstance(entry, EMGAcquisition) for entry in value):
                self._acquisitions = {}
                for entry in value:
                    assert isinstance(entry, EMGAcquisition)
                    assert isinstance(entry.acquisition_id, str)
                    self._acquisitions.update({entry.acquisition_id: entry})
        else:
            raise TypeError(
                "Field `Acquisitions` must be a list of EMGAcquisition objects"
            )

    def write(self, output_path: os.PathLike | str) -> None:
        """
        Write task-level EMG files.

        Parameters
        ----------
        output_path : os.PathLike | str
            The path where the output files will be written.
        """
        write_entities(output_path, self.acquisitions.values())
        # TODO check if right
        # where is json sidecar "*_emg.json" written? (recording)


def parse_emg_json_sidecar(sidecar_path: pathlib.Path) -> dict:
    """
    Split an EMG JSON sidecar into task, hardware, institution, and EMG blocks.

    Parameters
    ----------
    sidecar_path : pathlib.Path
        Path to an EMG JSON sidecar file.

    Returns
    -------
    dict
        Grouped metadata blocks keyed by ``task``, ``hardware``,
        ``institution``, and ``emg``.
    """
    with sidecar_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
        task_description = {}
        hardware_description = {}
        institution_description = {}
        emg_description = {}
        for key, value in data.items():
            if re.match(r"^Task[A-Z].*|^Instructions", key):
                task_description[key] = value
            elif re.match(
                r"^Device[A-Z].*|^(Electrode)?Manufacturer.*|^SoftwareVersions", key
            ):
                hardware_description[key] = value
            elif re.match(r"^Institution.*", key):
                institution_description[key] = value
            else:
                emg_description[key] = value

        return {
            "task": task_description,
            "hardware": hardware_description,
            "institution": institution_description,
            "emg": emg_description,
        }


def get_emg_channels(
    tsv_path: pathlib.Path | None,
    json_path: pathlib.Path | None,
) -> MutableSequence[EMGChannel]:
    """
    Build EMG channel objects from BIDS channel TSV/JSON files.

    Parameters
    ----------
    tsv_path : pathlib.Path | None
        Path to a BIDS ``*_channels.tsv`` file containing EMG channel definitions.
        If provided, channel data is parsed from the TSV file.
    json_path : pathlib.Path | None
        Path to a BIDS ``*_channels.json`` sidecar file containing channel metadata.
        If provided, column definitions are parsed from the JSON file.

    Returns
    -------
    MutableSequence[EMGChannel]
        List of :py:class:`EMGChannel` objects constructed from the parsed
        TSV and JSON metadata, with associated column information.

    See Also
    --------
    :py:class:`EMGChannel`
        Dataclass representing a single EMG channel definition.
    :py:func:`get_emg_electrodes`
        Similar function for building EMG electrode objects.

    Notes
    -----
    If both ``tsv_path`` and ``json_path`` are provided, column metadata from
    the JSON file is used to enrich the channel definitions from the TSV file.
    Either or both parameters can be ``None``, resulting in an empty list.
    """
    emg_channels: list[EMGChannel] = []
    columns = []

    if json_path:
        column_data = parse_json_sidecar(json_path)

        for column_name, column_values in column_data.items():
            columns.append(Column(name=column_name, **column_values))

    if tsv_path:
        data = parse_descriptive_tsv(tsv_path)
        for emg_channel in data:
            assert isinstance(emg_channel, dict), "Must be dicts in Generator."

            add_object_to_sequence(
                entity_list=emg_channels,
                entity_class=EMGChannel,
                columns=columns,
                **emg_channel,
            )

    return emg_channels


def get_emg_electrodes(
    tsv_path: pathlib.Path | None,
    json_path: pathlib.Path | None,
) -> MutableSequence[EMGElectrode]:
    """
    Build EMG electrode objects from BIDS electrode TSV/JSON files.

    Parameters
    ----------
    tsv_path : pathlib.Path | None
        Path to a BIDS ``*_electrodes.tsv`` file containing EMG electrode definitions.
        If provided, electrode data is parsed from the TSV file.
    json_path : pathlib.Path | None
        Path to a BIDS ``*_electrodes.json`` sidecar file containing electrode metadata.
        If provided, column definitions are parsed from the JSON file.

    Returns
    -------
    MutableSequence[EMGElectrode]
        List of :py:class:`EMGElectrode` objects constructed from the parsed
        TSV and JSON metadata, with associated column information.

    See Also
    --------
    :py:class:`EMGElectrode`
        Dataclass representing a single EMG electrode definition.
    :py:func:`get_emg_channels`
        Similar function for building EMG channel objects.

    Notes
    -----
    If both ``tsv_path`` and ``json_path`` are provided, column metadata from
    the JSON file is used to enrich the electrode definitions from the TSV file.
    Either or both parameters can be ``None``, resulting in an empty list.
    """
    emg_electrodes: list[EMGElectrode] = []
    columns = []

    if json_path:
        column_data = parse_json_sidecar(json_path)

        for column_name, column_values in column_data.items():
            columns.append(Column(name=column_name, **column_values))

    if tsv_path:
        data = parse_descriptive_tsv(tsv_path)
        for emg_electrode in data:
            assert isinstance(emg_electrode, dict), "Must be dicts in Generator."

            add_object_to_sequence(
                entity_list=emg_electrodes,
                entity_class=EMGElectrode,
                columns=columns,
                **emg_electrode,
            )

    return emg_electrodes


def _update_description_data(
    cls: EMGRecording | EMGRun | EMGAcquisition, file_name: str
) -> None:
    """
    Update inherited EMG metadata from nearby sidecars.

    Parameters
    ----------
    cls : EMGRecording or EMGRun or EMGAcquisition
        Object whose ``_description`` mapping should be updated.
    file_name : str
        Filename glob stem used to locate relevant sidecars.
    """
    _, json_path = get_tsv_json_files(cls.root, file_name + "emg")

    if json_path:
        if not cls._description:
            data = parse_emg_json_sidecar(json_path)
            data_clean = clean_dict(
                data,
                skip_keys_to_manipulate=ManipulateKeysOption.ALL_KEYS_MANIPULATE,
                string_manipulation=to_snakecase,
            )
            cls._description = data_clean
        else:
            data = parse_emg_json_sidecar(json_path)
            data_clean = clean_dict(
                data,
                skip_keys_to_manipulate=ManipulateKeysOption.ALL_KEYS_MANIPULATE,
                string_manipulation=to_snakecase,
            )
            cls._description.update(data_clean)
    else:
        warn(
            f"No EMG JSON sidecar file found for {cls._entity_name} {cls._entity_id} "
            f"in {cls.root}",
            FileNotFoundWarning,
        )

    tsv_path, json_path = get_tsv_json_files(cls.root, file_name + "electrodes")
    if tsv_path:
        electrodes = {"electrodes": get_emg_electrodes(tsv_path, json_path)}
        if not cls._description:
            cls._description = electrodes
        else:
            cls._description.update(electrodes)
    else:
        warn(
            f"No EMG electrodes TSV and JSON sidecar file found for {cls._entity_name} "
            f"{cls._entity_id} in {cls.root}",
            FileNotFoundWarning,
        )
