"""
Miscellaneous BIDS entities and data structures.

This module provides various utility classes for representing BIDS metadata
entities such as hardware, institutions, data columns, and filtering
specifications.
"""

#  Copyright (c) 2025 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

import os
import pathlib
from collections.abc import Iterable, Mapping, MutableMapping, MutableSequence, Sequence
from dataclasses import asdict, dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
)
from warnings import warn

import pandas as pd

from bidslab._typing import A
from bidslab.common.base import BaseAcquisition, Entity, check_entity_mismatch
from bidslab.settings import get_settings_value
from bidslab.utils.checks import check_if_valid_uri
from bidslab.utils.dict_manipulation import (
    ManipulateKeysOption,
    clean_dict,
    manipulate_dictkeys,
)
from bidslab.utils.exceptions import (
    FieldEntryNotValidError,
    TopLevelEntityNotLinkedWarning,
)
from bidslab.utils.helpers import (
    add_object_to_sequence,
    append_path,
    copy_file,
    get_entity_from_file,
    load_tsv_data,
    parse_descriptive_tsv,
    parse_json_sidecar,
    set_attr_from_dict,
    write_entities,
    write_json,
)
from bidslab.utils.string_manipulation import to_snakecase

if TYPE_CHECKING:
    from bidslab.common.specs_task import Task

FORMAT_ALLOWED_FIELD_ENTRIES = {
    "string",
    "number",
    "integer",
    "boolean",
    "index",
    "label",
    "date",
    "datetime",
    "time",
    "unit",
    "uri",
    "rrid",
    "bids_uri",
    "dataset_relative",
    "file_relative",
    "participant_relative",
    "stimuli_relative",
    "hed_version",
}


@dataclass(slots=True)
class Filter:
    """
    Represent a signal-processing filter specification.

    Attributes
    ----------
    name : str
        Human-readable filter name such as ``"bandpass"`` or ``"notch"``.
    parameters : MutableMapping[str, str]
        Mapping of parameter names to serialized values as they would appear in a
        BIDS JSON sidecar.

    See Also
    --------
    :py:class:`Hardware`
        Hardware metadata often documented alongside filter settings.

    Notes
    -----
    Filters are typically used to describe preprocessing or acquisition-chain
    operations applied to signal files in BIDS metadata.

    Examples
    --------
    >>> Filter(name="bandpass", parameters={"high_cutoff": "40", "low_cutoff": "1"})
    Filter(name='bandpass', parameters={'high_cutoff': '40', 'low_cutoff': '1'})
    """

    name: str
    parameters: MutableMapping[str, str]


@dataclass(slots=True)
class Level:
    """
    Represent a discrete categorical level for a BIDS TSV column.

    Attributes
    ----------
    level_name : str
        The name or value of the level.
    description : str
        A description of what this level represents.
    term_url : str, optional
        A URL to an ontology term defining this level.

    Raises
    ------
    ValueError
        If term_url is provided but is not a valid URI.

    See Also
    --------
    :py:class:`Column`
        Column metadata object that may aggregate multiple levels.

    Notes
    -----
    Levels are used in categorical columns to define the meaning of each
    distinct value. When ``term_url`` is provided, it is validated to ensure it
    conforms to URI standards expected by BIDS JSON sidecars.

    Examples
    --------
    >>> Level(level_name="left", description="Left-hand response")
    <Level name=left>
    """

    level_name: str
    description: str
    term_url: str | None = None

    def __post_init__(self) -> None:
        """
        Validate ontology metadata after initialization.

        Returns
        -------
        None
            The dataclass is validated in place.

        Raises
        ------
        ValueError
            Raised if :attr:`term_url` is present but is not a valid URI.

        Notes
        -----
        Validation is performed eagerly so invalid categorical metadata is caught
        before a :py:class:`Column` sidecar is written.
        """
        if self.term_url:
            check_if_valid_uri(self.term_url)

    def __repr__(self) -> str:
        """Return a string representation of the Level object."""
        return f"<Level name={self.level_name}>"


@dataclass(slots=True)
class Hardware:
    """
    Represent hardware or device metadata recorded in BIDS sidecars.

    Attributes
    ----------
    manufacturer : str, optional
        The name of the hardware manufacturer.
    manufacturers_model_name : str, optional
        The model name or number of the hardware.
    software_versions : str, optional
        The software version(s) running on the hardware.
    device_serial_number : str, optional
        The serial number of the device.

    See Also
    --------
    :py:class:`Institution`
        Institution-level metadata often reported together with hardware details.
    :py:class:`PhysioRecording`
        Recording class that can embed hardware information.

    Notes
    -----
    This class is used to document the specific hardware and software
    configuration used in data acquisition. It mirrors common manufacturer fields
    found across BIDS modality sidecars.

    Examples
    --------
    >>> Hardware(manufacturer="Elekta", manufacturers_model_name="VectorView")
    <Hardware manufacturer=Elekta model=VectorView>
    """

    manufacturer: str | None = None
    manufacturers_model_name: str | None = None
    software_versions: str | None = None
    device_serial_number: str | None = None

    def __repr__(self) -> str:
        """Return a string representation of the Hardware object."""
        return (
            f"<Hardware manufacturer={self.manufacturer} "
            f"model={self.manufacturers_model_name}>"
        )


@dataclass(slots=True)
class Institution:
    """
    Represent institution metadata associated with a BIDS acquisition site.

    Attributes
    ----------
    institution_name : str, optional
        The name of the institution.
    institution_address : str, optional
        The physical address of the institution.
    institutional_department_name : str, optional
        The name of the department within the institution.

    See Also
    --------
    :py:class:`Hardware`
        Acquisition-device metadata often stored alongside institution details.

    Notes
    -----
    This class is used to document the institution(s) responsible for
    data acquisition and processing. The fields correspond to common optional
    keys in BIDS sidecar metadata.

    Examples
    --------
    >>> Institution(institution_name="University Hospital")
    <Institution name=University Hospital>
    """

    institution_name: str | None = None
    institution_address: str | None = None
    institutional_department_name: str | None = None

    def __repr__(self) -> str:
        """Return a string representation of the Institution object."""
        return f"<Institution name={self.institution_name}>"


class Column:
    """
    Represents a data column specification in a BIDS TSV file.

    This class describes the properties of a column in a tabular (TSV) data
    file, including its name, format, units, and categorical levels.

    Parameters
    ----------
    name : str
        The name of the column as it appears in the TSV file.
    **kwargs : str | int | float | Mapping | Iterable
        Additional attributes to set on the column, such as long_name,
        description, format, units, etc.

    Attributes
    ----------
    column_name : str
        The name of the column.
    long_name : str, optional
        A longer, more descriptive name for the column.
    description : str, optional
        A description of what the column contains.
    format : str, optional
        The data format of the column values. Must be one of the values in
        :py:const:`FORMAT_ALLOWED_FIELD_ENTRIES`.
    units : str, optional
        The units of measurement for numeric columns.
    delimiter : str, optional
        The delimiter used to separate multiple values in a single cell.
    term_url : str, optional
        A URL to an ontology term defining this column.
    hed : str | Mapping[str, str], optional
        HED (Hierarchical Event Descriptors) tags for this column.
    maximum : int | float, optional
        The maximum value allowed in this column.
    minimum : int | float, optional
        The minimum value allowed in this column.

    Raises
    ------
    FieldEntryNotValidError
        If the format is not a valid BIDS format type.
    ValueError
        If term_url is provided but is not a valid URI.

    See Also
    --------
    :py:class:`Level`
        Categorical value definitions attached through :py:attr:`levels`.
    :py:class:`bidslab.common.specs_phenotype.PhenotypeColumn`
        Specialized phenotype-table column metadata.

    Notes
    -----
    The format property uses a custom setter to validate against allowed
    BIDS formats. Term URLs are validated when provided unless validation is
    explicitly overridden in settings. Levels support categorical-column
    documentation as described in BIDS JSON sidecars.

    Examples
    --------
    >>> Column(name="trial_type", format="string", levels={"go": "Go trial"})
    <Column name=trial_type format=string>
    """

    def __init__(
        self, name: str, **kwargs: str | int | float | Mapping | Iterable
    ) -> None:
        self.column_name: str = name

        self.long_name: str | None = None
        self.description: str | None = None
        self._format: str | None = None
        self.units: str | None = None
        self.delimiter: str | None = None
        self.term_url: str | None = None
        self.hed: str | Mapping[str, str] | None = None
        self.maximum: int | float | None = None
        self.minimum: int | float | None = None

        if get_settings_value("SUPPORT_OLD_VERSIONS"):
            self.unit: str | None = None

        self._levels: Iterable[Level] | None = None

        set_attr_from_dict(self, kwargs)

        if self.term_url and not get_settings_value("OVERRIDE_VALIDATION"):
            check_if_valid_uri(self.term_url)

    def __repr__(self) -> str:
        """Return a string representation of the Column object."""
        return f"<Column name={self.column_name} format={self.format}>"

    @property
    def format(self) -> str | None:
        # numpydoc ignore=RT01
        """Get the data format of the column values."""
        return self._format

    @format.setter
    def format(self, value: str) -> None:
        # numpydoc ignore=GL08
        if value not in FORMAT_ALLOWED_FIELD_ENTRIES:
            raise FieldEntryNotValidError(
                f"Field `Format` must be one of {FORMAT_ALLOWED_FIELD_ENTRIES}"
            )
        self._format = value

    @property
    def levels(self) -> Iterable[Level] | None:
        # numpydoc ignore=RT01
        """Get the categorical levels defined for this column."""
        return self._levels

    @levels.setter
    def levels(self, value: Mapping | Iterable[Level]) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, Mapping):
            self._levels = []
            for key, val in value.items():
                if isinstance(val, Mapping):
                    val = {
                        to_snakecase(level_key): level_val
                        for level_key, level_val in val.items()
                    }
                    level = Level(level_name=key, **val)
                else:
                    level = Level(level_name=key, description=val)

                self._levels.append(level)
        elif isinstance(value, Iterable) and all(isinstance(v, Level) for v in value):
            self._levels = value
        else:
            raise TypeError("Field `Levels` must be a list of Level objects")


@dataclass
class Event:
    """
    Represent an Event.

    Parameters
    ----------
    onset : float
        Onset (in seconds) of the event.
    duration : float
        Duration of the event (measured from onset) in seconds.
    **kwargs : Any
        Keyword arguments containing additional events metadata.

    Attributes
    ----------
    onset : float
        Onset (in seconds) of the event.
    duration : float
        Duration of the event (measured from onset) in seconds.
    columns : dict[str, Any]
        Dictionary containing column information.
    """

    def __init__(
        self,
        onset: float,
        duration: float,
        **kwargs: Any,
    ) -> None:
        self.onset: float = onset

        self.duration: float = duration

        self.columns: dict[str, Any] | None = None

        for key, value in kwargs.items():
            setattr(self, key, value)


class Recording(Entity):
    """
    Represents a recording from a single physiological measurement device.

    This is a base class for different types of physiological recordings
    (e.g., cardiac, respiratory, electromyographic). It manages the data
    and metadata for a single recording session.

    Parameters
    ----------
    base_path : os.PathLike | str
        The file system path to the directory containing recording data.
    recording_id : str
        The unique identifier for this recording.
    sampling_frequency : int | float
        The sampling frequency of the recording in Hz.
    virtual_entity : bool
        Parameter to distinguish virtual and real entities.

    Attributes
    ----------
    recording_id : str
        The unique identifier for the recording.
    sampling_frequency : int | float
        The sampling frequency in Hz.
    root : pathlib.Path
        The file system path to the recording directory.

    See Also
    --------
    PhysioRecording : A subclass for physiological recordings with columns.
    Run : The Run entity that contains Recording objects.

    Notes
    -----
    Recordings are typically associated with a :py:class:`Run` entity and contain
    physiological data recorded during an experimental task or resting period.
    Sample tables are loaded lazily from BIDS physio TSV files when
    :py:attr:`data` is accessed.

    Examples
    --------
    >>> recording = Recording(
    ...     base_path="ses-01",
    ...     recording_id="resp",
    ...     sampling_frequency=100,
    ... )
    >>> recording.recording_id
    'resp'
    """

    def __init__(
        self,
        base_path: os.PathLike | str,
        recording_id: str,
        sampling_frequency: int | float,
        virtual_entity: bool = False,
    ):
        super().__init__(
            _entity_id=recording_id,
            _entity_name="recording",
            _virtual_entity=virtual_entity,
        )
        self.recording_id: str = self._entity_id
        self.sampling_frequency: int | float = sampling_frequency

        self.root: pathlib.Path = pathlib.Path(base_path)

        self._run: Run | None = None

        self._data: Any | None = None

    @property
    def run(self) -> "Run | None":
        # numpydoc ignore=RT01
        """Get the parent Run object for this Recording."""
        if self._run:
            return self._run

        warn("Recording is not linked to a Run object.", TopLevelEntityNotLinkedWarning)
        return self._run

    @run.setter
    def run(self, value: "Run") -> None:
        # numpydoc ignore=GL08
        self._run = value

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
        entities.append(self.recording_id)
        return entities

    # def write(self, output_path: os.PathLike | str) -> None:
    #    # TODO: implement writing of basic Recording data
    #    if not get_settings_value("IGNORE_NOT_IMPLEMENTED"):
    #        raise NotImplementedError


class PhysioRecording(Recording):
    """
    Represents a physiological recording with defined columns.

    This class extends Recording to include column specifications and
    optional hardware information, typically used for data like cardiac
    rate, respiratory rate, or other physiological measurements.

    Parameters
    ----------
    base_path : os.PathLike | str
        The file system path to the directory containing recording data.
    recording_id : str
        The unique identifier for this recording.
    sampling_frequency : int
        The sampling frequency of the recording in Hz.
    start_time : int | float
        The start time of the recording relative to some reference point.
    columns : MutableSequence[Column]
        The column specifications for the data in this recording.
    physio_type : str, optional
        Defines the specific type of physiological recording.
    hardware : Hardware, optional
        Information about the hardware used for this recording.
    virtual_entity : bool
        Parameter to distinguish virtual and real entities.

    Attributes
    ----------
    start_time : int | float
        The start time of the recording.
    columns : MutableSequence[Column]
        The column specifications.
    physio_type : str | None
        The specific type of physiological recording.
    hardware : Hardware | None
        The hardware information.

    See Also
    --------
    Recording : The parent class for all recording types.
    Column : The column specification class.
    Hardware : Information about recording hardware.

    Notes
    -----
    PhysioRecording is typically used for recordings with well-defined column
    structures, as opposed to generic recording objects. It aligns with BIDS
    physiological recording sidecars that describe sampling frequency, start
    time, and channel columns.

    Examples
    --------
    >>> cols = [Column(name="cardiac", units="mV")]
    >>> PhysioRecording("ses-01", "cardiac", 1000, 0.0, cols)
    """

    def __init__(
        self,
        base_path: os.PathLike | str,
        recording_id: str,
        sampling_frequency: int,
        start_time: int | float,
        columns: MutableSequence[Column],
        physio_type: str | None = None,
        hardware: Hardware | None = None,
        virtual_entity: bool = False,
    ):
        super().__init__(
            base_path=base_path,
            recording_id=recording_id,
            sampling_frequency=sampling_frequency,
            virtual_entity=virtual_entity,
        )

        self.start_time: int | float = start_time
        self.columns: MutableSequence[Column] = columns
        self.physio_type: str | None = physio_type
        self.hardware: Hardware | None = hardware

        self._data: Any | None = None
        self._events: Sequence[Event] | None = None

    @property
    def data(self) -> pd.DataFrame:
        # numpydoc ignore=RT01
        """Get the data of the physio recording."""
        if self._data is None:
            # load data
            files = self.root.glob("*physio.tsv.gz")
            entities = self.get_top_level_entities()
            for file in files:
                # test if file is valid
                if check_entity_mismatch(
                    file.name.removesuffix("_physio.tsv.gz"), entities
                ):
                    self._data = load_tsv_data(path=file)
                    return self._data
        return self._data

    @data.setter
    def data(self, value: pd.DataFrame) -> None:
        # numpydoc ignore=GL08
        self._data = value

    @property
    def events(self) -> Sequence[Event] | None:
        # numpydoc ignore=RT01
        """Load or return cached physioevents sequence."""
        if not self._events:
            self._events = get_events_from_files(
                self, self.root, file_ending="physioevents"
            )

        return self._events

    @events.setter
    def events(self, value: Sequence[Event]) -> None:
        # numpydoc ignore=GL08
        self._events = value

    def write(self, output_path: os.PathLike | str) -> None:
        """
        Write physio recording files.

        Parameters
        ----------
        output_path : os.PathLike | str
            The path where the output files will be written.
        """
        output_path_json = append_path(output_path, "_physio.json")
        output_path_tsv = append_path(output_path, "_physio.tsv.gz")

        # write data into _physio.tsv.gz
        data_tsv = self.data
        data_tsv.to_csv(
            output_path_tsv,
            sep="\t",
            index=False,
            header=False,
            compression="gzip",
        )

        # write json sidecar
        description = self.__dict__.copy()
        description.pop("_data", None)
        description.pop("_events", None)
        description.pop("recording_id", None)
        description.pop("columns", None)
        description.pop("hardware", None)
        if self.hardware is not None:
            hardware_description = asdict(self.hardware)
            description.update(hardware_description)

        description = clean_dict(description)

        columns = self.columns
        column_names = []
        for column in columns:
            column_dict = column.__dict__.copy()
            column_names.append(column_dict.pop("column_name"))
            column_dict = clean_dict(
                column_dict,
                skip_keys_to_manipulate=ManipulateKeysOption.NO_MANIPULATION,
            )
            if column_dict:
                description[column.column_name] = column_dict

        if column_names:
            description["Columns"] = column_names
        write_json(description, output_path_json)

        # write physioevents
        if self.events:
            write_events_to_files(
                self,
                self.events,
                output_path,
                file_ending="physioevents",
                compressed=True,
            )


class StimRecording(Recording):
    """
    Represents a stim recording with defined columns.

    This class extends Recording to include column specifications
    used for Continuously-sampled, stimulus-related signals.

    Parameters
    ----------
    base_path : os.PathLike | str
        The file system path to the directory containing recording data.
    recording_id : str
        The unique identifier for this recording.
    sampling_frequency : int
        The sampling frequency of the recording in Hz.
    start_time : int | float
        The start time of the recording relative to some reference point.
    columns : MutableSequence[Column]
        The column specifications for the data in this recording.
    virtual_entity : bool
        Parameter to distinguish virtual and real entities.
    **kwargs
        Optional recording metadata.

    Attributes
    ----------
    start_time : int | float
        The start time of the recording.
    columns : MutableSequence[Column]
        The column specifications.
    sampling_frequency : int
        The sampling frequency of the recording in Hz.

    See Also
    --------
    Recording : The parent class for all recording types.
    Column : The column specification class.
    """

    def __init__(
        self,
        base_path: os.PathLike | str,
        recording_id: str,
        sampling_frequency: int | float,
        start_time: int | float,
        columns: MutableSequence[Column],
        virtual_entity: bool = False,
        **kwargs: Any,
    ):
        super().__init__(
            base_path=base_path,
            recording_id=recording_id,
            sampling_frequency=sampling_frequency,
            virtual_entity=virtual_entity,
        )

        self.root: pathlib.Path = pathlib.Path(base_path)
        self.start_time: int | float = start_time
        self.columns: MutableSequence[Column] = columns
        self.sampling_frequency: int | float = sampling_frequency

        self._data: Any | None = None

        for key, value in kwargs.items():
            setattr(self, key, value)

    @property
    def data(self) -> Any | None:
        # numpydoc ignore=RT01
        """Get the data of the stim recording."""
        if self._data is None:
            # load data
            folders = [self.root]
            path = self.root
            target = self.get_top_level_entities()[0]
            while path.name != target:
                path = path.parent
                folders.append(path)
            path = path.parent
            folders.append(path)

            files: list[pathlib.Path] = []
            for folder in folders:
                files = files + list(folder.glob("*_stim.tsv.gz"))

            entities = self.get_top_level_entities()
            for file in files:
                # test if file is valid
                if check_entity_mismatch(
                    file.name.removesuffix("_stim.tsv.gz"), entities
                ):
                    self._data = load_tsv_data(path=file)
                    return self._data
        return self._data

    @data.setter
    def data(self, value: pd.DataFrame) -> None:
        # numpydoc ignore=GL08
        self._data = value

    def write(self, output_path: os.PathLike | str) -> None:
        """
        Write stim recording files.

        Parameters
        ----------
        output_path : os.PathLike | str
            The path where the output files will be written.
        """
        output_path_json = append_path(output_path, "_stim.json")
        output_path_tsv = append_path(output_path, "_stim.tsv.gz")

        # write tsv.gz
        data_tsv = self.data
        if data_tsv is not None:
            data_tsv.to_csv(
                output_path_tsv,
                sep="\t",
                index=False,
                header=False,
                compression="gzip",
            )

        # write json sidecar
        description = self.__dict__.copy()
        description.pop("data", None)
        description.pop("recording_id", None)
        description.pop("columns", None)

        columns = self.columns
        column_names = []
        for column in columns:
            column_dict = column.__dict__.copy()
            column_names.append(column_dict.pop("column_name"))
            column_dict = clean_dict(
                column_dict,
                skip_keys_to_manipulate=ManipulateKeysOption.NO_MANIPULATION,
            )
            if column_dict:
                description[column.column_name] = column_dict

        if column_names:
            description["columns"] = column_names
        description = clean_dict(description)
        write_json(description, output_path_json)


class Run(Entity, Generic[A]):
    """
    Represents a single experimental run or session.

    A Run is a continuous acquisition period within an acquisition context.
    It can contain physiological recordings, event markers, and other
    related data.

    Parameters
    ----------
    base_path : os.PathLike | str
        The file system path to the directory containing run data.
    run_id : int
        The numeric identifier for this run (must be an integer index).
    virtual_entity : bool
        Parameter to distinguish virtual and real entities.
    **kwargs : Any
        Additional attributes to set on the run.

    Attributes
    ----------
    run_id : str
        The run identifier as a string.
    root : pathlib.Path
        The file system path to the run directory.

    Raises
    ------
    TypeError
        If run_id is not an integer.

    See Also
    --------
    Acquisition : The parent acquisition entity that contains runs.
    Recording : Physiological recordings within a run.

    Notes
    -----
    Run IDs must be integers and are used to index multiple runs within
    a single acquisition context. The ID is stored internally as a string
    for compatibility with BIDS naming conventions.

    Examples
    --------
    >>> run = Run(base_path="ses-01", run_id=1)
    >>> run.run_id
    '1'
    """

    def __init__(
        self,
        base_path: os.PathLike | str,
        run_id: int,
        virtual_entity: bool = False,
        **kwargs: Any,
    ):
        if not isinstance(run_id, int):
            raise TypeError("run_id must be an index of type integer")
        run_id_str = str(run_id)
        super().__init__(
            _entity_id="run-" + run_id_str,
            _entity_name="run",
            _virtual_entity=virtual_entity,
        )
        self.run_id: str = self._entity_id

        self.root: pathlib.Path = pathlib.Path(base_path)

        self._acquisition: A | None = None

        self._physio: dict[str, PhysioRecording] | None = None
        self._stims: dict[str, StimRecording] | None = None

        set_attr_from_dict(self, kwargs)

    def __repr__(self):
        """Return a string representation of the Run entity."""
        return f"Run id={self.run_id}"

    @property
    def acquisition(self) -> A | None:
        # numpydoc ignore=RT01
        """Get the parent Acquisition object for this Run."""
        if self._acquisition:
            return self._acquisition

        warn(
            "Run is not linked to a Acquisition object.", TopLevelEntityNotLinkedWarning
        )
        return self._acquisition

    @acquisition.setter
    def acquisition(self, value: A) -> None:
        # numpydoc ignore=GL08
        self._acquisition = value

    @property
    def physio(self) -> dict[str, PhysioRecording] | None:
        # numpydoc ignore=RT01
        """Get physiological recordings associated with this Run."""
        if self._physio is None:
            recording_labels = get_recordings_from_files(
                self, self.root, "physio.tsv.gz"
            )
            if not recording_labels:
                return None
            self._physio = {}

            # make files a list and append all possible
            # files in higher directories
            folders = [self.root]
            path = self.root
            target = self.get_top_level_entities()[0]
            while path.name != target:
                path = path.parent
                folders.append(path)
            path = path.parent
            folders.append(path)

            files: list[pathlib.Path] = []
            for folder in folders:
                files = files + list(folder.glob("*_physio.json"))

            for key, value in recording_labels.items():
                # get description (load json sidecar)
                entitylist = self.get_top_level_entities()
                entitylist.append(key)

                description = {}
                for file in files:
                    if check_entity_mismatch(
                        file.stem.removesuffix("_physio"),
                        entitylist,
                    ):
                        description = parse_json_sidecar(file)
                        break

                # create the entity with the loaded description
                if description:
                    # TODO create hardware and columns as class
                    description = manipulate_dictkeys(description, to_snakecase)
                    sampling_frequency = description.pop("sampling_frequency", None)
                    start_time = description.pop("start_time", None)
                    physio_type = description.pop("physio_type", None)
                    hardware = Hardware(
                        manufacturer=description.pop("maunfacturer", None),
                        manufacturers_model_name=description.pop(
                            "manufacturers_model_name", None
                        ),
                        device_serial_number=description.pop(
                            "device_serial_number", None
                        ),
                        software_versions=description.pop("software_versions", None),
                    )
                    column_names = description.pop("columns", None)
                    columns = []

                    columns = [
                        Column(column_name, **description.pop(column_name, {}))
                        for column_name in column_names
                    ]

                    self._physio[key] = PhysioRecording(
                        recording_id=key,
                        virtual_entity=value,
                        base_path=self.root,
                        sampling_frequency=sampling_frequency,
                        start_time=start_time,
                        physio_type=physio_type,
                        hardware=hardware,
                        columns=columns,
                        **description,
                    )
                    self._physio[key].run = self
                else:
                    raise FileNotFoundError

        return self._physio

    @physio.setter
    def physio(self, value: Sequence[dict] | Sequence[PhysioRecording]) -> None:
        # numpydoc ignore=GL08
        self._physio = {}
        for entry in value:
            if isinstance(entry, dict):
                self._physio.update(entry)
            elif isinstance(entry, PhysioRecording):
                self._physio.update({entry.recording_id: entry})

    @property
    def stims(self) -> dict[str, StimRecording] | None:
        # numpydoc ignore=RT01
        """Return stim recordings associated with the run."""
        if self._stims is None:
            recording_labels = get_recordings_from_files(self, self.root, "stim.tsv.gz")
            if not recording_labels:
                return None
            self._stims = {}

            # make files a list and append all possible
            # files in higher directories
            folders = [self.root]
            path = self.root
            target = self.get_top_level_entities()[0]
            while path.name != target:
                path = path.parent
                folders.append(path)
            path = path.parent
            folders.append(path)

            files = []
            for folder in folders:
                files = files + list(folder.glob("*_stim.json"))

            for key, value in recording_labels.items():
                # get description (load json sidecar)
                entitylist = self.get_top_level_entities()
                entitylist.append(key)

                description = {}
                for file in files:
                    if check_entity_mismatch(
                        file.stem.removesuffix("_stim"),
                        entitylist,
                    ):
                        description = parse_json_sidecar(file)
                        break

                # create the entity with the loaded description
                if description:
                    description = manipulate_dictkeys(description, to_snakecase)
                    sampling_frequency = description.pop("sampling_frequency", None)
                    start_time = description.pop("start_time", None)
                    column_names = description.pop("columns", None)
                    columns = []

                    columns = [
                        Column(column_name, **description.pop(column_name, {}))
                        for column_name in column_names
                    ]

                    self._stims[key] = StimRecording(
                        virtual_entity=value,
                        recording_id=key,
                        base_path=self.root,
                        sampling_frequency=sampling_frequency,
                        start_time=start_time,
                        columns=columns,
                    )
                    self._stims[key].run = self
                else:
                    raise FileNotFoundError

        return self._stims

    @stims.setter
    def stims(self, value: dict[str, StimRecording]) -> None:
        # numpydoc ignore=GL08
        self._stims = value

    def get_top_level_entities(self) -> list[str | Any]:
        """
        Method to get all top level entities.

        Returns
        -------
        list
            A list containing the entity_ids of all top level entities.
        """
        assert self.acquisition is not None
        entities = self.acquisition.get_top_level_entities()
        entities.append(self.run_id)
        return entities

    def write(self, output_path: os.PathLike | str) -> None:
        """
        Write the run to disk.

        Parameters
        ----------
        output_path : os.PathLike | str
            The file system path where the run should be written.
        """
        if self.physio:
            write_entities(output_path, self.physio.values())
        if self.stims:
            write_entities(output_path, self.stims.values())


class Acquisition(BaseAcquisition):
    """
    Represents an acquisition context within a datatype.

    An Acquisition groups multiple runs of the same acquisition, such as
    repeated measurements with the same equipment or parameters. Acquisitions
    are organized by datatype (e.g., MEG, EEG) and are associated with tasks.

    Parameters
    ----------
    base_path : os.PathLike | str
        The file system path to the acquisition directory.
    acquisition_id : str
        The unique identifier for the acquisition.
    virtual_entity : bool
        Parameter to distinguish virtual and real entities.

    Attributes
    ----------
    acquisition_id : str
        The unique identifier for the acquisition.
    root : pathlib.Path
        The file system path to the acquisition directory.
    runs : MutableSequence[Run]
        The runs associated with this acquisition.

    See Also
    --------
    Run : Individual run objects within an acquisition.
    Task : Task entities associated with acquisitions.

    Notes
    -----
    Acquisitions automatically discover and load runs from the file system.
    If no runs are found, a default run is created.

    Examples
    --------
    >>> acquisition = Acquisition(base_path="ses-01/meg", acquisition_id="acq-highres")
    >>> acquisition.runs
    [Run id=run-0]
    """

    def __init__(
        self,
        base_path: os.PathLike | str,
        acquisition_id: str,
        virtual_entity: bool = False,
    ):
        super().__init__(
            base_path=base_path,
            acquisition_id=acquisition_id,
            virtual_entity=virtual_entity,
        )

        self._task: Task | None = None

    @property
    def runs(self) -> dict[str, Run]:
        # numpydoc ignore=RT01
        """Get the runs associated with this Acquisition."""
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
                run_id_int = int(run_id.split("-")[1])
                self._runs.update(
                    {
                        f"run-{run_id_int}": Run(
                            run_id=run_id_int,
                            base_path=self.root,
                            acquisition=self,
                        )
                    }
                )
            # If no runs are found, add a default one
            if not self._runs:
                self._runs.update(
                    {
                        "run-0": Run(
                            run_id=0,
                            base_path=self.root,
                            acquisition=self,
                        )
                    }
                )

        return self._runs

    @runs.setter
    def runs(self, value: Sequence[int | Run] | dict[str, Run]) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, Sequence):
            if all(isinstance(entry, int) for entry in value):
                self._runs = {}
                for entry in value:
                    assert isinstance(entry, int)  # for mypy
                    self._runs.update(
                        {
                            f"run-{entry}": Run(
                                run_id=entry, base_path=self.root, acquisition=self
                            )
                        }
                    )
            elif all(isinstance(v, Run) for v in value):
                self._runs = {}
                for entry in value:
                    assert isinstance(entry, Run)  # for mypy
                    self._runs.update({entry.run_id: entry})
        elif isinstance(value, dict):
            self._runs = value
        raise TypeError("Field `Runs` must be a list or dict of Run objects")

    @property
    def task(self) -> "Task | None":
        # numpydoc ignore=RT01
        """Get the task associated with this Acquisition."""
        if self._task:
            return self._task

        warn(
            "Acquisition is not linked to a Task object.",
            TopLevelEntityNotLinkedWarning,
        )
        return self._task

    @task.setter
    def task(self, value: "Task") -> None:
        # numpydoc ignore=GL08
        self._task = value

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


def get_recordings_from_files(
    run: Run, base_path: os.PathLike | str, file_ending: str
) -> dict[str, bool]:
    """
    Get recording ids from file names.

    Parameters
    ----------
    run : Run
        The ruun object associated with the recordings.
    base_path : os.Pathike | str
        The initial path to find the files.
    file_ending : str
        The ending of the files including the extension.

    Returns
    -------
    dict[str, bool]
        A dict containing the recording_ids and if they are virtual_entities.
    """
    labels = {}

    base_path = pathlib.Path(base_path)
    files = base_path.glob(f"*_{file_ending}")
    for file in files:
        try:
            label = get_entity_from_file(file, "recording")["recording"]
            entities = run.get_top_level_entities()
            entities.append(f"recording-{label}")
            if check_entity_mismatch(
                file.name.removesuffix(f"_{file_ending}"), entities
            ):
                labels[f"recording-{label}"] = False

        except KeyError:
            continue

    if not labels:
        files = base_path.glob(f"*_{file_ending}")
        for file in files:
            # check if a file matches
            if check_entity_mismatch(
                file.name.removesuffix(f"_{file_ending}"), run.get_top_level_entities()
            ):
                labels["recording-00"] = True
                break

    return labels


def get_events_from_files(
    cls: Recording | Run, base_path: os.PathLike | str, file_ending: str = "events"
) -> MutableSequence[Event] | None:
    """
    Get Events from files.

    Parameters
    ----------
    cls : Recording | Run
        The object containing the events.
    base_path : os.Pathike | str
        The initial path to find the files.
    file_ending : str, optional
        An optional different file ending (used for physioevents).

    Returns
    -------
    MutableSequence[Event]
        A sequence containing the events.
    """
    base_path = pathlib.Path(base_path)

    events: MutableSequence[Event] = []
    columns: MutableMapping[Any, Any] = {}

    # get list of top level entities
    entities = cls.get_top_level_entities()

    # sequence of all possible folders
    # in the correct input order (deepest to dataset_root)
    folders_json = [base_path]
    path = base_path
    target = entities[0]
    while path.name != target:
        path = path.parent
        folders_json.append(path)
    path = path.parent
    folders_json.append(path)

    folders_tsv = [base_path, base_path.parent]

    for folder in folders_json:
        if columns == {}:
            # get all possible files with _events.json
            files_json = list(folder.glob(f"*_{file_ending}.json"))
            filenames_json = [f.name for f in files_json]
            file_entities_json = [
                f.removesuffix(f"_{file_ending}.json") for f in filenames_json
            ]

            # check for entity mismatches and use first one working
            for file in file_entities_json:
                if check_entity_mismatch(file, entities):
                    # load .json file and save it
                    columns = parse_json_sidecar(
                        folder / (file + f"_{file_ending}.json")
                    )
                    break
        else:
            break

    for folder in folders_tsv:
        if events == []:
            # get all possible files with _events.tsv
            files_tsv = list(folder.glob(f"*_{file_ending}.tsv"))
            files_tsv.extend(list(folder.glob(f"*_{file_ending}.tsv.gz")))
            filenames_tsv = [f.stem.removesuffix(f"_{file_ending}") for f in files_tsv]

            # check for entity mismatches and use first one working
            for file in filenames_tsv:
                if check_entity_mismatch(file, entities):
                    # load .tsv file and save it
                    try:
                        data = parse_descriptive_tsv(
                            tsv_path=folder / (file + f"_{file_ending}.tsv")
                        )
                    except FileNotFoundError:
                        data = parse_descriptive_tsv(
                            tsv_path=folder / (file + f"_{file_ending}.tsv.gz")
                        )
                    for event in data:
                        add_object_to_sequence(
                            entity_list=events,
                            entity_class=Event,
                            columns=columns,
                            **event,
                        )
                    break
        else:
            break

    return events


def write_events_to_files(
    cls: Recording | Run,
    events: Sequence[Event],
    output_path: os.PathLike | str,
    file_ending: str = "events",
    compressed: bool = False,
) -> None:
    """
    Write a sequence of events to disk.

    Parameters
    ----------
    cls : Recording | Run
        The object containing the events.
    events : Sequence[Event]
        The event sequence.
    output_path : os.Pathike | str
        The output path for the file.
    file_ending : str, optional
        An optional different file ending (used for physioevents).
    compressed : bool
        Compression of the output file.
    """
    output_path_json = append_path(output_path, f"_{file_ending}.json")
    if compressed:
        output_path_tsv = append_path(output_path, f"_{file_ending}.tsv.gz")
    else:
        output_path_tsv = append_path(output_path, f"_{file_ending}.tsv")

    # write json sidecar
    columns = events[0].columns

    description = clean_dict(columns)
    write_json(content=description, output_path=output_path_json)

    # write stimuli and tsv data

    data_tsv = pd.DataFrame(event.__dict__ for event in events)
    data_tsv = data_tsv.drop(columns=["columns"], errors="ignore")

    if "stim_file" in data_tsv.columns:
        # find root of the dataset
        entities = cls.get_top_level_entities()
        output_dataset_root = pathlib.Path(output_path)
        target = entities[0]
        while output_dataset_root.name != target:
            output_dataset_root = output_dataset_root.parent
        output_dataset_root = output_dataset_root.parent

        dataset_root = cls.root
        while dataset_root.name != target:
            dataset_root = dataset_root.parent
        dataset_root = dataset_root.parent
        # create stimuli directory
        stimuli_path = pathlib.Path(output_dataset_root / "stimuli")
        if not stimuli_path.exists():
            stimuli_path.mkdir(parents=True, exist_ok=True)

        # copy files into the stimuli directory
        unique_files = set(data_tsv["stim_file"])
        for file in unique_files:
            copy_file(
                source_path=dataset_root / "stimuli" / str(file),
                destination_path=stimuli_path,
            )

    if compressed:
        data_tsv.to_csv(
            output_path_tsv, sep="\t", index=False, header=True, compression="gzip"
        )
    else:
        data_tsv.to_csv(output_path_tsv, sep="\t", index=False, header=True)
