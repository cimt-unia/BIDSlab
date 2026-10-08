"""
IEEG extension models for BIDS intracranial electroencephalography datasets.

This module implements iEEG-specific hardware, coordinate system, channel,
electrode, recording, acquisition, and task models together with helper
functions for parsing EEG sidecars and tabular metadata.
"""

#  Copyright (c) 2026 by Lukas Behammer, Tobias Noak
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
    Entity,
    Event,
    Filter,
    Hardware,
    Institution,
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

IEEG_CHANNEL_TYPE_ALLOWED_FIELD_ENTRIES = {
    "EEG",
    "ECOG",
    "SEEG",
    "DBS",
    "VEOG",
    "HEOG",
    "EOG",
    "ECG",
    "EMG",
    "TRIG",
    "AUDIO",
    "PD",
    "EYEGAZE",
    "PUPIL",
    "MISC",
    "SYSCLOCK",
    "ADC",
    "DAC",
    "REF",
    "OTHER",
}


@dataclass(slots=True)
class IEEGHardware(Hardware):
    """
    Extend generic hardware metadata with iEEG electrode manufacturer fields.

    Attributes
    ----------
    electrode_manufacturer : str | None, optional
        Manufacturer of the electrodes.
    electrode_manufacturers_model_name : str | None, optional
        Manufacturer-reported model name or catalog number for the electrodes.

    See Also
    --------
    :py:class:`IEEGRun`
        Run-level container that links hardware and channel metadata.
    """

    electrode_manufacturer: str | None = None
    electrode_manufacturers_model_name: str | None = None


@dataclass(slots=True)
class IEEGCoordinateSystem:
    """
    Represent an IEEG coordinate system.

    Attributes
    ----------
    name : str
        Local identifier used to reference the coordinate system.
    ieeg_coordinate_system : str
        Coordinate-system keyword defined by the BIDS standard, for example
        ``CapTrak``, ``EEGLAB`` or ``Other``.
    ieeg_coordinate_units : str
        Spatial units used for electrode coordinates, typically ``mm`` or ``cm``.
    intended_for : str | None, optional
        The paths to files for which the associated object is intended to be used.
    ieeg_coordinate_system_description : str | None, optional
        Required explanatory text when ``eeg_coordinate_system`` is ``Other``.
    ieeg_coordinate_processing_description : str | None, optional
        Has any post-processing been done on the electrode positions.
    ieeg_coordinate_processing_reference : str | None, optional
        A reference to a paper that defines in more detail the method used to
        localize the electrodes and to post-process the electrode positions.

    Raises
    ------
    FieldMissingError
        If a required description or anchoring field is omitted.
    """

    name: str

    ieeg_coordinate_system: str
    ieeg_coordinate_units: str
    intended_for: str | Sequence[str] | None = None
    ieeg_coordinate_system_description: str | None = None
    ieeg_coordinate_processing_description: str | None = None
    ieeg_coordinate_processing_reference: str | None = None

    def __post_init__(self):
        """Validate coordinate system configuration."""
        if (
            self.ieeg_coordinate_system == "Other"
            and not self.ieeg_coordinate_system_description
        ):
            raise FieldMissingError(
                "Field `iEEGCoordinateSystemDescription` must be present if field "
                "`iEEGCoordinateSystem` is 'Other'"
            )

    def __repr__(self) -> str:
        """Return a string representation of the IEEGCoordinateSystem object."""
        return f"<IEEGCoordinateSystem name={self.name}>"

    def __hash__(self) -> int:
        """Return a hash of the coordinate system."""
        return id(self)


class IEEGChannel:
    """
    Represent one IEEG channel definition from ``*_channels.tsv``.

    Parameters
    ----------
    name : str
        Channel name used in tabular metadata and renamed sample data columns.
    type : str
        BIDS channel type.
    units : str
        Measurement unit such as ``uV``, ``mV``, or ``V``.
    low_cutoff : int | float
        Frequencies used for the high-pass filter applied to the channel.
    high_cutoff : int | float
        Frequencies used for the low-pass filter applied to the channel.
    **kwargs
        Optional metadata fields.

    Raises
    ------
    FieldEntryNotValidError
        If ``type`` is not allowed by the EEG extension.

    See Also
    --------
    :py:class:`IEEGRun`
        Run object that owns channel definitions and sample data.
    """

    def __init__(
        self,
        name: str,
        type: str,  # noqa: A002
        units: str,
        low_cutoff: int | float,
        high_cutoff: int | float,
        **kwargs: Any,
    ):
        self.name: str = name
        self._type: str = type
        self.units: str = units
        self.low_cutoff: int | float = low_cutoff
        self.high_cutoff: int | float = high_cutoff

        self.reference: str | None = None
        self.group: str | None = None
        self.sampling_frequency: int | float | None = None
        self.description: str | None = None
        self.notch: str | None = None
        self.status: str | None = None
        self.status_description: str | None = None
        self.columns: Sequence[Column] | None = None

        set_attr_from_dict(self, kwargs)

    def __repr__(self) -> str:
        """Return a string representation of the IEEGChannel object."""
        return f"<IEEGChannel name={self.name}>"

    @property
    def type(self) -> str | None:
        # numpydoc ignore=RT01
        """Return the validated IEEG channel type."""
        return self._type

    @type.setter
    def type(self, value: str) -> None:
        # numpydoc ignore=GL08
        if value not in IEEG_CHANNEL_TYPE_ALLOWED_FIELD_ENTRIES:
            raise FieldEntryNotValidError(
                f"Field `Type` must be one of {IEEG_CHANNEL_TYPE_ALLOWED_FIELD_ENTRIES}"
            )
        self._type = value


class IEEGElectrode:
    """
    Represent one IEEG electrode definition from ``*_electrodes.tsv``.

    Parameters
    ----------
    name : str
        Electrode label used in electrode tables and channel references.
    x : int | float
        X coordinate of the electrode center in the associated coordinate system.
    y : int | float
        Y coordinate of the electrode center in the associated coordinate system.
    z : int | float
        Z coordinate of the electrode center in the associated coordinate system.
    size : int | float
        Surface area of the electrode, units MUST be in mm^2.
    **kwargs
        Optional metadata including electrode type, material, impedance.

    See Also
    --------
    :py:class:`IEEGChannel`
        Channel metadata that can reference the electrode by name.

    Notes
    -----
    Use electrodes to document sensor placement on the skin, in a grid, or in a
    fine-wire configuration. Coordinate and impedance metadata are especially
    important for reproducible placement descriptions and quality control.

    Examples
    --------
    Describe a surface electrode

    >>> electrode = IEEGElectrode(
    ...     name="E01",
    ...     x=12.5,
    ...     y=31.0,
    ...     z=0.0,
    ...     size=2,
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
        z: int | float,
        size: int | float,
        **kwargs: Any,
    ):
        self.name: str = name
        self.x: int | float = x
        self.y: int | float = y
        self.z: int | float = z
        self.size: int | float = size

        self.material: str | None = None
        self.manufacturer: str | None = None
        self.group: str | None = None
        self.hemisphere: str | None = None
        self.type: str | None = None
        self.impedance: int | float | None = None
        self.dimension: str | None = None
        self.columns: Sequence[Column] | None = None

        set_attr_from_dict(self, kwargs)

    def __repr__(self) -> str:
        """Return a string representation of the IEEGElectrode object."""
        return f"<IEEGElectrode name={self.name}>"


class IEEGSpace(Entity):
    """
    Represent an IEEG space containing coordinate systems and electrodes.

    Parameters
    ----------
    base_path : os.PathLike | str
        Directory containing run-level EEG files.
    space_id : str
        Space identifier used to resolve ``space-<label>`` entities.
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
    :py:class:`IEEGRun`
        Parent run that groups spaces.
    """

    def __init__(
        self,
        base_path: os.PathLike | str,
        space_id: str,
        virtual_entity: bool = False,
        **kwargs: Any,
    ):
        description = kwargs.pop("_description", {})
        if not isinstance(description, MutableMapping):
            raise TypeError(
                "Parameter type for argument `_description` must be MutableMapping"
            )
        self._description: MutableMapping = description

        super().__init__(space_id, "space", virtual_entity)

        self.root: pathlib.Path = pathlib.Path(base_path)

        self.space_id: str = self._entity_id  # !: This is required

        self._electrodes: MutableSequence[IEEGElectrode] | None = None
        self._coordinate_system: IEEGCoordinateSystem | None = None

        self._run: IEEGRun | None = None

        # Try to set attributes from arguments
        set_attr_from_dict(self, kwargs)

        self._update_description()

        # Update values from self._description
        if self._description:
            self._electrodes = self._description.pop("electrodes", None)

    @property
    def run(self) -> "Run | None":
        # numpydoc ignore=RT01
        """Get the parent Run object for this Space."""
        if self._run:
            return self._run

        warn("Space is not linked to a Run object.", TopLevelEntityNotLinkedWarning)
        return self._run

    @run.setter
    def run(self, value: "Run") -> None:
        # numpydoc ignore=GL08
        self._run = value

    @property
    def electrodes(self) -> MutableSequence[IEEGElectrode] | None:
        # numpydoc ignore=RT01
        """Return electrode definitions associated with the space."""
        return self._electrodes

    @electrodes.setter
    def electrodes(self, value: MutableSequence[Mapping | IEEGElectrode]) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, MutableSequence):
            if all(isinstance(entry, Mapping) for entry in value):
                self._electrodes = []
                for entry in value:
                    assert isinstance(entry, Mapping)  # for mypy
                    self._electrodes.append(IEEGElectrode(**entry))
            elif all(isinstance(e, IEEGElectrode) for e in value):
                self._electrodes = value  # type: ignore[assignment]  # mypy cannot type narrow on all()
        else:
            raise TypeError(
                "Field `Electrodes` must be a list of IEEGElectrodes object"
            )

    @property
    def coordinate_system(self) -> IEEGCoordinateSystem | None:
        # numpydoc ignore=RT01
        """Return coordinate systems associated with the space."""
        if self._coordinate_system is None:
            # load corrdsystems from files
            entities = self.get_top_level_entities()

            # get all possible files with _coordsystem.json
            files_json = list(self.root.glob("*_coordsystem.json"))
            filenames_json = [f.name for f in files_json]
            file_entities_json = [
                f.removesuffix("_coordsystem.json") for f in filenames_json
            ]

            # check for entity mismatches and use first one working
            for file in file_entities_json:
                if check_entity_mismatch(file, entities):
                    # load .json file and save it
                    data = parse_json_sidecar(self.root / (file + "_coordsystem.json"))
                    data = clean_dict(data, string_manipulation=to_snakecase)
                    self._coordinate_system = IEEGCoordinateSystem(
                        name=self.space_id.removeprefix("space-"),
                        **data,
                    )
                    return self._coordinate_system

        return self._coordinate_system

    @coordinate_system.setter
    def coordinate_system(self, value: IEEGCoordinateSystem) -> None:
        # numpydoc ignore=GL08
        self._coordinate_system = value

    def _update_description(self) -> None:
        """Refresh inherited description metadata for the run."""
        file_name = f"*_{self.space_id}_*"
        _update_description_data(self, file_name)

    def write(self, output_path: os.PathLike | str) -> None:
        """
        Write space-level IEEG files.

        Parameters
        ----------
        output_path : os.PathLike | str
            The path where the output files will be written.
        """
        #  write electrodes files (_electrodes.tsv, _electrodes.json)+
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

        # write coordinate system file (_coordsystem.json)
        if self.coordinate_system:
            output_path_coordsystem = append_path(output_path, "_coordsystem.json")
            coord_dict = asdict(self.coordinate_system)
            _ = coord_dict.pop("name", None)
            coord_dict = clean_dict(coord_dict)
            write_json(coord_dict, output_path=output_path_coordsystem)

    def get_top_level_entities(self) -> list[str | Any]:
        """
        Method to get all top level entities.

        Returns
        -------
        list
            A list containing the entity_ids of all top level entities.
        """
        assert self.run is not None
        entities = self.run.get_top_level_entities()
        entities.append(self.space_id)
        return entities

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
        for ieeg_electrode in self.electrodes if self.electrodes else []:
            electrode_dict = ieeg_electrode.__dict__.copy()

            coordinate_system = electrode_dict.pop("coordinate_system", None)
            if isinstance(coordinate_system, IEEGCoordinateSystem):
                electrode_dict["coordinate_system"] = coordinate_system.name

            electrode_dict.pop("columns")

            electrode_dict = clean_dict(electrode_dict)
            electrodes_dataframe = pd.concat(
                [electrodes_dataframe, pd.DataFrame([electrode_dict])],
                ignore_index=True,
            )
        electrodes_dataframe.dropna(axis=1, how="all", inplace=True)
        return electrodes_dataframe


class IEEGRun(Run):
    """
    Represent an IEEG run containing one or more recordings.

    Parameters
    ----------
    base_path : os.PathLike | str
        Directory containing run-level EEG files.
    run_id : int
        Numeric run identifier used to resolve ``run-<index>`` entities.
    ieeg_reference : str,
        General description of the reference scheme.
    sampling_frequency : int | float,
        Sampling frequency of all the data in the recording.
    power_line_frequency : int | float | str,
        Frequency of the power grid at the geographical location of the instrument.
    software_filters : MutableMapping[str, Filter] | str,
        Software filtering description stored in the EEG sidecar.
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
    :py:class:`IEEGAcquisition`
        Parent acquisition that groups runs.
    """

    def __init__(
        self,
        base_path: os.PathLike | str,
        run_id: int,
        ieeg_reference: str,
        sampling_frequency: int | float,
        power_line_frequency: int | float | str,
        software_filters: MutableMapping[str, Filter] | str,
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
            base_path=base_path, run_id=run_id, virtual_entity=virtual_entity
        )

        self.ieeg_reference: str = ieeg_reference
        self.sampling_frequency: int | float = sampling_frequency
        self.power_line_frequency: int | float | str = power_line_frequency
        self.software_filters: MutableMapping[str, Filter] | str = software_filters

        self.dc_offset_correction: str | None = None
        self.hardware_filters: MutableMapping[str, Filter] | str | None = None
        self.ecog_channel_count: int | None = None
        self.seeg_channel_count: int | None = None
        self.eeg_channel_count: int | None = None
        self.eog_channel_count: int | None = None
        self.ecg_channel_count: int | None = None
        self.emg_channel_count: int | None = None
        self.misc_channel_count: int | None = None
        self.trigger_channel_count: int | None = None

        self.recording_duration: float | None = None
        self.recording_type: str | None = None
        self.epoch_length: float | None = None

        self.ieeg_ground: str | None = None
        self.ieeg_placement_scheme: str | Sequence[str] | None = None
        self.subject_artefact_description: str | None = None

        self.electrical_stimulation: bool | None = None
        self.electrical_stimulation_parameters: str | None = None

        self._hardware: IEEGHardware | None = None
        self._institution: Institution | None = None

        self._channels: MutableSequence[IEEGChannel] | None = None
        self._spaces: dict[str, IEEGSpace] | None = None

        self._data: pd.DataFrame | None = None
        self._events: Sequence[Event] | None = None

        self._acquisition: IEEGAcquisition | None = None

        # Try to set attributes from arguments
        set_attr_from_dict(self, kwargs)

        self._update_description()

        # Update values from self._description
        if self._description:
            ieeg_description = self._description.pop("ieeg", {})
            hardware_description = self._description.pop("hardware", {})
            institution_description = self._description.pop("institution", {})
            _ = self._description.pop("task", None)
            set_attr_from_dict(self, {**ieeg_description})
            self.hardware = hardware_description
            self.institution = institution_description

    # def __repr__(self) -> str:
    #     return f"<Run id=run-{self.run_id}>"

    @property
    def spaces(self) -> dict[str, IEEGSpace]:
        # numpydoc ignore=RT01
        """Return spaces associated with the run."""
        if not self._spaces:
            self._spaces = {}
            files = self.root.iterdir()
            space_ids = set()
            for file in files:
                try:
                    space_ids.add(
                        get_entity_from_file(
                            file,
                            "space",
                        )["space"]
                    )
                except KeyError:
                    continue
            for space_id in space_ids:
                self._spaces.update(
                    {
                        "space-" + space_id: IEEGSpace(
                            space_id="space-" + space_id,
                            base_path=self.root,
                            run=self,
                            electrodes=self._description.get("electrodes", None),
                        )
                    }
                )

            # If no spaces are found, add a default one
            if not self._spaces:
                self._spaces.update(
                    {
                        "space-00": IEEGSpace(
                            space_id="space-00",
                            base_path=self.root,
                            run=self,
                            virtual_entity=True,
                            electrodes=self._description.get("electrodes", None),
                        )
                    }
                )

        return self._spaces

    @spaces.setter
    def spaces(self, value: dict[str | IEEGSpace]) -> None:
        # numpydoc ignore=GL08
        self._spaces = value

    @property
    def hardware(self) -> IEEGHardware | None:
        # numpydoc ignore=RT01
        """Return hardware metadata linked to the EEG run."""
        return self._hardware

    @hardware.setter
    def hardware(self, value: Mapping | IEEGHardware) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, Mapping):
            hardware_data = {}
            for k, v in value.items():
                hardware_data[to_snakecase(k)] = v
            self._hardware = IEEGHardware(**hardware_data)
        elif isinstance(value, IEEGHardware):
            self._hardware = value
        else:
            raise TypeError("Field `Hardware` must be an IEEGHardware object")

    @property
    def institution(self) -> Institution | None:
        # numpydoc ignore=RT01
        """Return institution metadata linked to the EEG run."""
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
    def channels(self) -> MutableSequence[IEEGChannel] | None:
        # numpydoc ignore=RT01
        """Return channel definitions associated with the run."""
        return self._channels

    @channels.setter
    def channels(self, value: MutableSequence[Mapping | IEEGChannel]) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, MutableSequence):
            if all(isinstance(entry, Mapping) for entry in value):
                self._channels = []
                for entry in value:
                    assert isinstance(entry, Mapping)  # for mypy
                    self._channels.append(IEEGChannel(**entry))
            elif all(isinstance(entry, IEEGChannel) for entry in value):
                self._channels = value  # type: ignore[assignment]  # mypy cannot type narrow on all()
        else:
            raise TypeError("Field `Channels` must be a list of IEEGChannel object")

    @property
    def data(self) -> pd.DataFrame:
        # numpydoc ignore=RT01
        """Load or return cached IEEG sample data."""
        if self._data is None:
            file_name = f"*{self.acquisition.task.task_id}*"
            file_name += (
                f"_{self.acquisition.acquisition_id}"
                if not self.acquisition._virtual_entity
                else ""
            )
            file_name += f"_{self.run_id}" if not self._virtual_entity else ""
            edf_path, _ = get_edf_json_files(
                self.root,
                file_name + "_eeg",
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
        """Refresh inherited description metadata for the run."""
        file_name = f"*_{self.run_id}_*"
        _update_description_data(self, file_name)

    def write(self, output_path: os.PathLike | str) -> None:
        """
        Write run-level iEEG files.

        Parameters
        ----------
        output_path : os.PathLike | str
            The path where the output files will be written.
        """
        # write eeg json sidecar and eeg data
        output_path_eeg_json = append_path(output_path, "_eeg.json")
        eeg_description = self.__dict__.copy()
        eeg_description.pop("spaces", None)
        eeg_description.pop("channels", None)
        eeg_description.pop("events", None)
        eeg_description.pop("run_id", None)
        eeg_description.pop("_description", None)

        # eeg_software_filters = eeg_description.pop("software_filters", None)
        # eeg_hardware_filters = eeg_description.pop("hardware_filters", None)

        eeg_hardware = eeg_description.pop("_hardware", None)
        if eeg_hardware is not None:
            eeg_description.update(asdict(self._hardware))

        eeg_institution = eeg_description.pop("_institution", None)
        if eeg_institution is not None:
            eeg_description.update(asdict(self._institution))

        # add task information to eeg_description
        task_description = self.acquisition.task.__dict__.copy()
        task_description.pop("acquisitions", None)
        task_description.pop("_description", None)
        task_description.pop("task_id", None)
        task_description.pop("root", None)
        task_description.pop(
            "_acquisitions", None
        )  # idk why it is not removed by clean_dict
        eeg_description.update(task_description)

        eeg_description = clean_dict(eeg_description)
        write_json(eeg_description, output_path_eeg_json)

        # write spaces (contains coord systems and electrodes)
        if self.spaces is not None:
            write_entities(output_path, self.spaces.values())

        # write events files
        if self.events:
            write_events_to_files(self, self.events, output_path)

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

        # write photo files if available (_photo.jpg/png/tif)
        photo_files = self.root.glob("*_photo.*")
        for photo in photo_files:
            copy_file(
                source_path=photo,
                destination_path=output_path.parent,
            )

        super().write(output_path)

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
            if isinstance(coordinate_system, IEEGCoordinateSystem):
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


class IEEGAcquisition(BaseAcquisition):
    """
    Represent an IEEG acquisition beneath a task.

    Parameters
    ----------
    base_path : os.PathLike | str
        Directory containing acquisition-level EEG files.
    acquisition_id : str
        BIDS acquisition label, usually ``acq-<label>``.
    task : IEEGTask
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
    :py:class:`IEEGTask`
        Parent task containing the acquisition.
    :py:class:`IEEGRun`
        Run objects created under the acquisition.

    Notes
    -----
    The acquisition acts as the bridge between task-level metadata and run-level
    recordings. It refreshes inherited description blocks and lazily constructs
    :py:class:`IEEGRun` objects from files in the acquisition directory.

    Examples
    --------
    Create or load an acquisition and enumerate runs

    >>> acquisition = IEEGAcquisition(
    ...     base_path="sub-01/ses-01/eeg",
    ...     acquisition_id="acq-grip",
    ... )
    >>> run_ids = [run.run_id for run in acquisition.runs]
    """

    def __init__(
        self,
        base_path: os.PathLike | str,
        acquisition_id: str,
        task: "IEEGTask",
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

        self._task: IEEGTask | None = task

        self._update_description()

        set_attr_from_dict(self, kwargs)

    @property
    def runs(self) -> dict[str, IEEGRun]:
        # numpydoc ignore=RT01
        """Return runs associated with the acquisition."""
        if not self._runs:
            assert self.task is not None
            file_name = f"*{self.task.task_id}"
            file_name += f"_{self.acquisition_id}" if not self._virtual_entity else ""

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
                        "run-" + run_id: IEEGRun(
                            run_id=int(run_id),
                            base_path=self.root,
                            acquisition=self,
                            hardware=self._description.get("hardware", None),
                            institution=self._description.get("institution", None),
                            channels=get_ieeg_channels(
                                *get_tsv_json_files(
                                    self.root,
                                    file_name + f"_run-{run_id}_channels",
                                )
                            ),
                            electrodes=self._description.get("electrodes", None),
                            **self._description.get("ieeg", None),
                        )
                    }
                )

            # If no runs are found, add a default one
            if not self._runs:
                self._runs.update(
                    {
                        "run-0": IEEGRun(
                            run_id=0,
                            base_path=self.root,
                            acquisition=self,
                            _description=self._description,
                            virtual_entity=True,
                            **self._description.get("ieeg", {}),
                        )
                    }
                )

        return self._runs

    @runs.setter
    def runs(self, value: MutableSequence[IEEGRun] | dict[str, IEEGRun]) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, MutableSequence):
            if all(isinstance(v, IEEGRun) for v in value):
                self._runs = {}
                for v in value:
                    assert isinstance(v, IEEGRun)
                    assert isinstance(v.run_id, str)
                    self._runs.update({v.run_id: v})
        elif isinstance(value, dict):
            self._runs = value
        else:
            raise TypeError("Field `Runs` must be a list of EEGRun objects")

    @property
    def task(self) -> "IEEGTask | None":
        # numpydoc ignore=RT01
        """Get the parent :py:class:`IEEGTask` linked to the acquisition."""
        if self._task:
            return self._task

        warn(
            "Acquisition is not linked to a IEEGTask object.",
            TopLevelEntityNotLinkedWarning,
        )
        return self._task

    @task.setter
    def task(self, value: "IEEGTask") -> None:
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


class IEEGTask(BaseTask):
    """
    Represent a BIDS IEEG task composed of acquisitions.

    Parameters
    ----------
    base_path : os.PathLike | str
        Root directory containing task-specific EEG files.
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
    :py:class:`IEEGAcquisition`
        Acquisition objects belonging to the task.
    :py:meth:`write`
        Task-level write entry point for future IEEG serialization support.

    Examples
    --------
    Load an IEEG task and inspect its hierarchy

    >>> task = IEEGTask(base_path="sub-01/ses-01/eeg", task_name="grip")
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

        self.cog_atlas_id: str | None = kwargs.pop("cog_atlas_id", None)
        self.cog_po_id: str | None = kwargs.pop("cog_po_id", None)

        super().__init__(
            base_path=base_path, task_name=task_name, virtual_entity=False, **kwargs
        )

        self._acquisitions: dict[str, IEEGAcquisition] | None = None

    @property
    def acquisitions(self) -> dict[str, IEEGAcquisition]:
        # numpydoc ignore=RT01
        """Return acquisitions discovered for the EEG task."""
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
                        "acq-" + acquisition_label: IEEGAcquisition(
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
                        "acq-00": IEEGAcquisition(
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
        self, value: MutableSequence[str] | MutableSequence[IEEGAcquisition]
    ) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, MutableSequence):
            if all(isinstance(entry, str) for entry in value):
                self._acquisitions = {}
                for entry in value:
                    assert isinstance(entry, str)  # for mypy
                    self._acquisitions.update(
                        {
                            entry: IEEGAcquisition(
                                acquisition_id=entry,
                                base_path=self.root,
                                task=self,
                                _description=self._description,
                            )
                        }
                    )
            elif all(isinstance(entry, IEEGAcquisition) for entry in value):
                self._acquisitions = {}
                for entry in value:
                    assert isinstance(entry, IEEGAcquisition)
                    assert isinstance(entry.acquisition_id, str)
                    self._acquisitions.update({entry.acquisition_id: entry})
        else:
            raise TypeError(
                "Field `Acquisitions` must be a list of IEEGAcquisition objects"
            )

    def write(self, output_path: os.PathLike | str) -> None:
        """
        Write task-level EEG files.

        Parameters
        ----------
        output_path : os.PathLike | str
            The path where the output files will be written.
        """
        write_entities(output_path, self.acquisitions.values())


def parse_ieeg_json_sidecar(sidecar_path: pathlib.Path) -> dict:
    """
    Split an IEEG JSON sidecar into task, hardware, institution, and EEG blocks.

    Parameters
    ----------
    sidecar_path : pathlib.Path
        Path to an IEEG JSON sidecar file.

    Returns
    -------
    dict
        Grouped metadata blocks keyed by ``task``, ``hardware``,
        ``institution``, and ``ieeg``.
    """
    with sidecar_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
        task_description = {}
        hardware_description = {}
        institution_description = {}
        eeg_description = {}
        for key, value in data.items():
            if re.match(r"^Task[A-Z].*|^Instructions|^Cog[A-Z].*", key):
                task_description[key] = value
            elif re.match(
                r"^Device[A-Z].*|^(Electrode)?Manufacturer.*|^SoftwareVersions", key
            ):
                hardware_description[key] = value
            elif re.match(r"^Institution.*", key):
                institution_description[key] = value
            else:
                eeg_description[key] = value

        return {
            "task": task_description,
            "hardware": hardware_description,
            "institution": institution_description,
            "ieeg": eeg_description,
        }


def get_ieeg_channels(
    tsv_path: pathlib.Path | None,
    json_path: pathlib.Path | None,
) -> MutableSequence[IEEGChannel]:
    """
    Build IEEG channel objects from BIDS channel TSV/JSON files.

    Parameters
    ----------
    tsv_path : pathlib.Path | None
        Path to a BIDS ``*_channels.tsv`` file containing IEEG channel definitions.
        If provided, channel data is parsed from the TSV file.
    json_path : pathlib.Path | None
        Path to a BIDS ``*_channels.json`` sidecar file containing channel metadata.
        If provided, column definitions are parsed from the JSON file.

    Returns
    -------
    MutableSequence[IEEGChannel]
        List of :py:class:`IEEGChannel` objects constructed from the parsed
        TSV and JSON metadata, with associated column information.

    See Also
    --------
    :py:class:`IEEGChannel`
        Dataclass representing a single IEEG channel definition.
    :py:func:`get_ieeg_electrodes`
        Similar function for building IEEG electrode objects.

    Notes
    -----
    If both ``tsv_path`` and ``json_path`` are provided, column metadata from
    the JSON file is used to enrich the channel definitions from the TSV file.
    Either or both parameters can be ``None``, resulting in an empty list.
    """
    eeg_channels: list[IEEGChannel] = []
    columns = []

    if json_path:
        column_data = parse_json_sidecar(json_path)

        for column_name, column_values in column_data.items():
            columns.append(Column(name=column_name, **column_values))

    if tsv_path:
        data = parse_descriptive_tsv(tsv_path)
        for eeg_channel in data:
            assert isinstance(eeg_channel, dict), "Must be dicts in Generator."

            add_object_to_sequence(
                entity_list=eeg_channels,
                entity_class=IEEGChannel,
                columns=columns,
                **eeg_channel,
            )

    return eeg_channels


def get_ieeg_electrodes(
    tsv_path: pathlib.Path | None,
    json_path: pathlib.Path | None,
) -> MutableSequence[IEEGElectrode]:
    """
    Build IEEG electrode objects from BIDS electrode TSV/JSON files.

    Parameters
    ----------
    tsv_path : pathlib.Path | None
        Path to a BIDS ``*_electrodes.tsv`` file containing EEG electrode definitions.
        If provided, electrode data is parsed from the TSV file.
    json_path : pathlib.Path | None
        Path to a BIDS ``*_electrodes.json`` sidecar file containing electrode metadata.
        If provided, column definitions are parsed from the JSON file.

    Returns
    -------
    MutableSequence[IEEGElectrode]
        List of :py:class:`EEGElectrode` objects constructed from the parsed
        TSV and JSON metadata, with associated column information.

    See Also
    --------
    :py:class:`IEEGElectrode`
        Dataclass representing a single IEEG electrode definition.
    :py:func:`get_ieeg_channels`
        Similar function for building IEEG channel objects.

    Notes
    -----
    If both ``tsv_path`` and ``json_path`` are provided, column metadata from
    the JSON file is used to enrich the electrode definitions from the TSV file.
    Either or both parameters can be ``None``, resulting in an empty list.
    """
    eeg_electrodes: list[IEEGElectrode] = []
    columns = []

    if json_path:
        column_data = parse_json_sidecar(json_path)

        for column_name, column_values in column_data.items():
            columns.append(Column(name=column_name, **column_values))

    if tsv_path:
        data = parse_descriptive_tsv(tsv_path)
        for eeg_electrode in data:
            assert isinstance(eeg_electrode, dict), "Must be dicts in Generator."

            add_object_to_sequence(
                entity_list=eeg_electrodes,
                entity_class=IEEGElectrode,
                columns=columns,
                **eeg_electrode,
            )

    return eeg_electrodes


def _update_description_data(
    cls: IEEGRun | IEEGAcquisition | IEEGSpace, file_name: str
) -> None:
    """
    Update inherited EEG metadata from nearby sidecars.

    Parameters
    ----------
    cls : EEGRun or EEGAcquisition
        Object whose ``_description`` mapping should be updated.
    file_name : str
        Filename glob stem used to locate relevant sidecars.
    """
    _, json_path = get_tsv_json_files(cls.root, file_name + "ieeg")

    if json_path:
        if not cls._description:
            data = parse_ieeg_json_sidecar(json_path)
            data_clean = clean_dict(
                data,
                skip_keys_to_manipulate=ManipulateKeysOption.ALL_KEYS_MANIPULATE,
                string_manipulation=to_snakecase,
            )
            cls._description = data_clean
        else:
            data = parse_ieeg_json_sidecar(json_path)
            data_clean = clean_dict(
                data,
                skip_keys_to_manipulate=ManipulateKeysOption.ALL_KEYS_MANIPULATE,
                string_manipulation=to_snakecase,
            )
            cls._description.update(data_clean)
    else:
        warn(
            f"No iEEG JSON sidecar file found for {cls._entity_name} {cls._entity_id} "
            f"in {cls.root}",
            FileNotFoundWarning,
        )

    tsv_path, json_path = get_tsv_json_files(cls.root, file_name + "electrodes")
    if tsv_path:
        electrodes = {"electrodes": get_ieeg_electrodes(tsv_path, json_path)}
        if not cls._description:
            cls._description = electrodes
        else:
            cls._description.update(electrodes)
    else:
        warn(
            f"No iEEG electrodes TSV and JSON sidecar file found for {cls._entity_name} "
            f"{cls._entity_id} in {cls.root}",
            FileNotFoundWarning,
        )
