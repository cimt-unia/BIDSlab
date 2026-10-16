"""
BIDS dataset specification models and serialization helpers.

This module defines the top-level :py:class:`Dataset` container together with
provenance metadata classes and helper functions for loading and writing
``dataset_description.json``, ``participants.tsv``, and phenotype files that
follow the Brain Imaging Data Structure (BIDS).
"""

#  Copyright (c) 2025 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

import os
import pathlib
from collections.abc import Mapping, MutableSequence, Sequence
from dataclasses import dataclass

import pandas as pd

from bidslab.common.specs_misc import Column
from bidslab.common.specs_phenotype import MeasurementTool, PhenotypeColumn
from bidslab.common.specs_summary import Participant
from bidslab.settings import get_settings_value
from bidslab.utils.checks import check_if_valid_uri, check_version
from bidslab.utils.dict_manipulation import (
    ManipulateKeysOption,
    add_levels_to_dict,
    clean_dict,
)
from bidslab.utils.exceptions import (
    FieldMissingError,
    VersionMismatchError,
)
from bidslab.utils.helpers import (
    add_object_to_sequence,
    copy_file,
    get_root_files,
    get_tsv_json_files,
    parse_descriptive_tsv,
    parse_json_sidecar,
    set_attr_from_dict,
    write_json,
)
from bidslab.utils.string_manipulation import to_snakecase

COLUMNS_TO_REMOVE_FROM_TSV = {
    "columns",
    "name",
    "description",
    "term_url",
    "_participant",
}


@dataclass(slots=True)
class SourceDataset:
    """
    Describe a source dataset referenced from a BIDS dataset description.

    Attributes
    ----------
    url : str | None
        URI pointing to the source dataset location.
    doi : str | None
        Persistent identifier for the source dataset.
    version : str | None
        Version string for the referenced dataset.

    Raises
    ------
    ValueError
        Raised by :py:func:`bidslab.utils.checks.check_if_valid_uri` if ``url``
        or ``doi`` is not a valid URI.

    See Also
    --------
    :py:class:`GeneratedBy`
        Provenance entries describing software used to create the dataset.
    :py:class:`Dataset`
        Top-level dataset container that owns source dataset metadata.

    Notes
    -----
    BIDS derivatives may list upstream datasets in the
    ``SourceDatasets`` field of ``dataset_description.json``.
    """

    url: str | None = None
    doi: str | None = None
    version: str | None = None

    def __post_init__(self) -> None:
        """
        Validate URI-like fields after initialization.

        Returns
        -------
        None
            URI fields are validated in place.

        Raises
        ------
        ValueError
            Raised if ``url`` or ``doi`` is not a valid URI.

        Notes
        -----
        Validation is performed eagerly so invalid provenance metadata is caught
        before the parent :py:class:`Dataset` is written.
        """
        if self.url:
            check_if_valid_uri(self.url)
        if self.doi:
            check_if_valid_uri(self.doi)

    def __repr__(self) -> str:
        """Return a string representation of the SourceDataset object."""
        return f"<SourceDataset url={self.url} doi={self.doi} version={self.version}>"


@dataclass(slots=True)
class Container:
    """
    Represent container metadata for a provenance entry.

    Attributes
    ----------
    type : str | None
        Container runtime type such as ``"docker"`` or ``"singularity"``.
    tag : str | None
        Version tag or image identifier.
    uri : str | None
        URI pointing to the container image or registry entry.

    Raises
    ------
    ValueError
        Raised by :py:func:`bidslab.utils.checks.check_if_valid_uri` when
        ``uri`` is malformed.

    See Also
    --------
    :py:class:`GeneratedBy`
        Provenance metadata that can embed container information.

    Notes
    -----
    Container metadata is commonly nested under ``GeneratedBy`` entries in BIDS
    derivative datasets.
    """

    type: str | None = None
    tag: str | None = None
    uri: str | None = None

    def __post_init__(self) -> None:
        """
        Validate the container URI after initialization.

        Returns
        -------
        None
            Container metadata is validated in place.

        Raises
        ------
        ValueError
            Raised if :attr:`uri` is not a valid URI.
        """
        if self.uri:
            check_if_valid_uri(self.uri)

    def __repr__(self) -> str:
        """Return a string representation of the Container object."""
        return f"<Container type={self.type} tag={self.tag} uri={self.uri}>"


class GeneratedBy:
    """
    Describe software provenance for a BIDS dataset or derivative.

    Parameters
    ----------
    **kwargs
        Keyword arguments mapped onto provenance fields such as ``name``,
        ``version``, ``description``, ``code_url``, and ``container``.

    Attributes
    ----------
    name : str | None
        Human-readable tool or workflow name. BIDS recommends ``"Manual"`` for
        manually created derivatives.
    version : str | None
        Version string for the generating software.
    description : str | None
        Plain-text description of the workflow or processing step.
    code_url : str | None
        URI to the source code or release page for the software.
    container : Container | None
        Optional container image metadata stored through the
        :py:attr:`container` property.

    Raises
    ------
    FieldMissingError
        If the required ``name`` field is missing.
    ValueError
        Raised by :py:func:`bidslab.utils.checks.check_if_valid_uri` if
        ``code_url`` is invalid.
    TypeError
        If :attr:`container` is assigned a value that is neither a mapping nor a
        :py:class:`Container` instance.

    See Also
    --------
    :py:class:`Container`
        Container metadata nested under provenance entries.
    :py:class:`Dataset`
        Top-level object exposing the :py:attr:`Dataset.generated_by` property.

    Notes
    -----
    ``GeneratedBy`` entries are part of the BIDS derivatives provenance model.
    """

    def __init__(self, **kwargs: str | Mapping | Container) -> None:
        self.name: str | None = None  # !: This is required
        self.version: str | None = None
        self.description: str | None = None
        self.code_url: str | None = None
        self._container: Container | None = None

        if kwargs:
            set_attr_from_dict(self, kwargs)

        if self.name is None:
            raise FieldMissingError("Field `Name` is required in GeneratedBy")

    def __post_init__(self) -> None:
        """
        Validate the code URL after initialization.

        Returns
        -------
        None
            Provenance metadata is validated in place.

        Raises
        ------
        ValueError
            Raised if :attr:`code_url` is not a valid URI.
        """
        if self.code_url:
            check_if_valid_uri(self.code_url)

    def __repr__(self) -> str:
        """Return a string representation of the GeneratedBy object."""
        return f"<GeneratedBy name={self.name} version={self.version}>"

    @property
    def container(self) -> Container | None:
        # numpydoc ignore=RT01
        """Get the container metadata attached to this provenance entry."""
        return self._container

    @container.setter
    def container(self, value: Mapping | Container) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, Mapping):
            self._container = Container(**value)
        elif isinstance(value, Container):
            self._container = value
        else:
            raise TypeError("Field `Container` must be a Container object")


class Dataset:
    """
    Represent a complete BIDS dataset rooted on disk.

    Parameters
    ----------
    root : os.PathLike
        Path to the dataset root directory on disk.
    bids_version : str
        The expected BIDS version for the dataset (for example ``'1.8.0'``).
    **kwargs
        Optional dataset-level metadata (these are assigned as attributes on
        the object). Typical keys mirror the fields in ``dataset_description.json``.

    Attributes
    ----------
    name : str | None
        Human-readable dataset name. Required for strict validation.
    bids_version : str
        Expected BIDS version for the dataset.
    hed_version : str | Sequence[str] | None
        HED version(s) used in the dataset.
    dataset_links : Mapping[str, str] | None
        Links BIDS URIs to dataset locations.
    dataset_type : str | None
        Type of dataset (for example, ``'raw'``, ``'derivative'``
        or ``'sourcedata'``).
    license : str | None
        License under which the dataset is shared.
    authors : Sequence[str] | None
        Sequence of dataset authors.
    keywords : Sequence[str] | None
        Sequence of keywords describing the dataset.
    acknowledgements : str | None
        Acknowledgements for the dataset.
    how_to_acknowledge : str | None
        Instructions on how to acknowledge the dataset.
    funding : Sequence[str] | None
        Sequence of funding sources for the dataset.
    ethics_approvals : Sequence[str] | None
        Sequence of ethics approval statements.
    references_and_links : Sequence[str] | None
        Sequence of references and links related to the dataset.
    dataset_doi : str | None
        DOI or persistent identifier for the dataset.
    generated_by : Sequence[GeneratedBy] | None
        Sequence of tools/software that generated or processed the dataset.
    source_datasets : Sequence[SourceDataset] | None
        Sequence of datasets referenced as sources.
    root : pathlib.Path
        Path object pointing to the dataset root.
    participants : Sequence[Participant]
        Sequence of participant objects in the dataset.

    Raises
    ------
    ValueError
        Raised by :py:func:`bidslab.utils.checks.check_if_valid_uri` when
        ``dataset_doi`` is provided but invalid.

    Warnings
    --------
    The instance stores several convenience path attributes such as
    :attr:`readme_path` and :attr:`phenotype_path` that are internal helpers and
    not formal BIDS metadata fields.

    See Also
    --------
    :py:func:`get_participants_from_files`
        Loader used by :py:attr:`participants`.
    :py:func:`get_phenotypes_from_files`
        Loader for phenotype measurement tables.

    Notes
    -----
    Raw and derivative datasets in BIDS must provide a
    ``dataset_description.json`` sidecar. Participant and phenotype metadata are
    loaded lazily from the dataset tree when accessed.

    Examples
    --------
    >>> dataset = Dataset(root="dataset", bids_version="1.10.0")
    >>> dataset.load()
    >>> dataset.participants
    [<Participant ...>]
    """

    def __init__(
        self, root: os.PathLike, bids_version: str, **kwargs: str | Mapping | Sequence
    ) -> None:
        self.name: str | None = None  # !: This is required
        self.bids_version: str = bids_version  # !: This is required
        self.hed_version: str | Sequence[str] | None = None
        self.dataset_links: Mapping[str, str] | None = None
        self.dataset_type: str | None = None
        self.license: str | None = None
        self.authors: Sequence[str] | None = None
        self.keywords: Sequence[str] | None = None
        self.acknowledgements: str | None = None
        self.how_to_acknowledge: str | None = None
        self.funding: Sequence[str] | None = None
        self.ethics_approvals: Sequence[str] | None = None
        self.references_and_links: Sequence[str] | None = None
        self.dataset_doi: str | None = None
        self._generated_by: Sequence[GeneratedBy] | None = None
        self._source_datasets: Sequence[SourceDataset] | None = None

        self.root: pathlib.Path = pathlib.Path(root)

        self.readme_path: pathlib.Path | None = None  # !: This is required
        self.citation_path: pathlib.Path | None = None
        self.changes_path: pathlib.Path | None = None
        self.license_path: pathlib.Path | None = None

        self.sourcedata_path: pathlib.Path | None = None
        self.derivatives_path: pathlib.Path | None = None
        self.code_path: pathlib.Path | None = None
        self.stimuli_path: pathlib.Path | None = None
        self.phenotype_path: pathlib.Path | None = None

        self._participants: dict[str, Participant] | None = None

        if kwargs:
            set_attr_from_dict(self, kwargs)

        if self.dataset_doi:
            check_if_valid_uri(self.dataset_doi)  # type: ignore[unreachable]

    def __repr__(self) -> str:
        """Return a string representation of the Dataset object."""
        return (
            f"<BIDSDataset name={self.name} path={self.root} "
            f"bids_version={self.bids_version}>"
        )

    @property
    def generated_by(self) -> Sequence[GeneratedBy] | None:
        # numpydoc ignore=RT01
        """Get provenance entries describing software that generated the dataset."""
        return self._generated_by

    @generated_by.setter
    def generated_by(self, value: Sequence[Mapping] | Sequence[GeneratedBy]) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, Sequence):
            if all(isinstance(entry, Mapping) for entry in value):
                self._generated_by = []
                for entry in value:
                    assert isinstance(entry, Mapping)  # for mypy
                    gen_by = GeneratedBy(**entry)

                    self._generated_by.append(gen_by)
            elif all(isinstance(entry, GeneratedBy) for entry in value):
                self._generated_by = value  # type: ignore[assignment]  # mypy cannot type narrow on all()
        else:
            raise TypeError("Field `GeneratedBy` must be a list of GeneratedBy objects")

    @property
    def source_datasets(self) -> Sequence[SourceDataset] | None:
        # numpydoc ignore=RT01
        """Get source dataset references for this dataset."""
        return self._source_datasets

    @source_datasets.setter
    def source_datasets(
        self, value: Sequence[Mapping] | Sequence[SourceDataset]
    ) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, Sequence):
            if all(isinstance(entry, Mapping) for entry in value):
                self._source_datasets = []
                for entry in value:
                    assert isinstance(entry, Mapping)  # for mypy
                    self._source_datasets.append(SourceDataset(**entry))
            elif all(isinstance(entry, SourceDataset) for entry in value):
                self._source_datasets = value  # type: ignore[assignment]  # mypy cannot type narrow on all()
        else:
            raise TypeError(
                "Field `SourceDatasets` must be a list of SourceDataset objects"
            )

    @property
    def participants(self) -> dict[str, Participant]:
        # numpydoc ignore=RT01
        """Get participants declared in the dataset."""
        if not self._participants:
            tsv_path, json_path = get_tsv_json_files(self.root, "participants")
            self._participants = get_participants_from_files(
                self, tsv_path=tsv_path, json_path=json_path
            )

            # If no participants are found, create a default one
            if len(self._participants) == 0:
                self._participants.update(
                    {
                        "sub-00": Participant(
                            base_path=self.root, participant_id="sub-00", dataset=self
                        )
                    }
                )

        return self._participants

    @participants.setter
    def participants(self, value: Sequence[Mapping] | Sequence[Participant]) -> None:
        # numpydoc ignore=GL08
        if isinstance(value, Sequence):
            if all(isinstance(entry, Mapping) for entry in value):
                self._participants = {}
                for entry in value:
                    assert isinstance(entry, Mapping)  # for mypy
                    self._participants.update(
                        {
                            entry.get("participant_id", "sub-01"): Participant(
                                base_path=self.root
                                / entry.get("participant_id", "sub-01"),
                                dataset=self,
                                **entry,
                            )
                        }
                    )
            elif all(isinstance(entry, Participant) for entry in value):
                self._participants = {}
                for entry in value:
                    assert isinstance(entry, Participant)  # for mypy
                    self._participants.update({entry.participant_id: entry})
        else:
            raise TypeError(
                "Field `Participants` must be a list of Participant objects"
            )

    def load(self) -> None:
        """
        Load dataset metadata from ``dataset_description.json``.

        Returns
        -------
        None
            This method updates the instance in place.

        Raises
        ------
        VersionMismatchError
            If the dataset sidecar declares a BIDS version that differs from the
            expected :attr:`bids_version`.
        FieldMissingError
            If required BIDS fields or files are missing and validation override
            is disabled.

        Warnings
        --------
        Validation behavior depends on the ``OVERRIDE_VALIDATION`` setting and
        may be less strict when explicitly configured.

        See Also
        --------
        :py:meth:`write`
            Persist dataset metadata back to disk.

        Notes
        -----
        The method also populates convenience path attributes via
        :py:func:`bidslab.utils.helpers.get_root_files`.
        """
        get_root_files(self)

        data = parse_json_sidecar(self.root / "dataset_description.json")

        # TODO: Check if necessary
        try:
            check_version(self, data.get("BIDSVersion", None))
        except VersionMismatchError:
            raise VersionMismatchError(
                f"The version of the dataset you tried to load "
                f"{data.get('BIDSVersion', None)} is not the same as the one you "
                f"specified {self.bids_version}."
            ) from None

        set_attr_from_dict(self, data)

        override_validation = get_settings_value("OVERRIDE_VALIDATION")

        if self.name is None and not override_validation:
            raise FieldMissingError("Field `Name` is required in Dataset")
        if self.readme_path is None and not override_validation:
            raise FieldMissingError("File `README` is required")

    def list_participants(self) -> pd.DataFrame:
        """
        Build a tabular summary of dataset participants.

        Returns
        -------
        pd.DataFrame
            DataFrame suitable for writing to ``participants.tsv``.

        See Also
        --------
        :py:meth:`write`
            Uses this method when serializing ``participants.tsv``.

        Notes
        -----
        Internal linkage fields and empty columns are removed before returning
        the table so the result conforms to BIDS ``participants.tsv`` column
        expectations.

        Examples
        --------
        >>> df = dataset.list_participants()
        >>> list(df.columns)
        ['participant_id', 'age', 'sex']
        """
        participants_dataframe = pd.DataFrame()
        for participant in self.participants.values():
            participant_dict = participant.__dict__.copy()
            participant_dict = clean_dict(
                participant_dict,
                skip_keys_to_manipulate=ManipulateKeysOption.ALL_KEYS_MANIPULATE,
            )

            _ = participant_dict.pop("columns", None)
            participants_dataframe = pd.concat(
                [participants_dataframe, pd.DataFrame([participant_dict])],
                ignore_index=True,
            )
        participants_dataframe.dropna(axis=1, how="all", inplace=True)
        return participants_dataframe

    def _columns(self) -> set[Column]:
        """
        Collect participant column definitions across the dataset.

        Returns
        -------
        set[Column]
            Unique :py:class:`~bidslab.common.specs_misc.Column` objects
            aggregated from all participants.

        Notes
        -----
        The returned set is used to build the ``participants.json`` sidecar that
        documents participant-level TSV columns under the BIDS inheritance model.
        """
        columns_set = set()
        for participant in self.participants.values():
            for column in participant.columns if participant.columns else []:
                columns_set.add(column)
        return columns_set

    def write(self, output_path: os.PathLike | str, overwrite: bool = False) -> None:
        """
        Write the dataset structure and metadata to disk.

        Parameters
        ----------
        output_path : os.PathLike | str
            Destination directory for the dataset. When falsy, :attr:`root` is
            used.
        overwrite : bool, optional
            If ``True``, allow writing into an existing directory.

        Returns
        -------
        None
            This method writes files and directories as side effects.

        Raises
        ------
        FileExistsError
            If ``output_path`` already exists and ``overwrite`` is ``False``.

        See Also
        --------
        :py:meth:`write_phenotype`
            Serialize phenotype measurement files.

        Notes
        -----
        This method writes ``dataset_description.json``, participant metadata,
        phenotype files, and participant/session content recursively while
        preserving the BIDS directory hierarchy rooted at ``output_path``.

        Examples
        --------
        >>> dataset.write("out-dataset", overwrite=True)
        """
        output_path = self.root if not output_path else output_path
        output_path = pathlib.Path(output_path)

        if output_path.exists() and not overwrite:
            raise FileExistsError(
                f"The output path {output_path} already exists. "
                f"Set `overwrite=True` to overwrite existing files."
            )

        if not output_path.exists():
            output_path.mkdir(parents=True, exist_ok=True)

        # write dataset description to "dataset_description.json"
        output_path_dataset_description = output_path / "dataset_description.json"
        dataset_description = self.__dict__.copy()
        files_to_copy = [
            dataset_description.pop("readme_path", None),
            dataset_description.pop("changes_path", None),
            dataset_description.pop("license_path", None),
            dataset_description.pop("citation_path", None),
        ]
        _ = dataset_description.pop("sourcedata_path", None)
        _ = dataset_description.pop("code_path", None)
        _ = dataset_description.pop("stimuli_path", None)
        _ = dataset_description.pop("phenotype_path", None)
        _ = dataset_description.pop("derivatives_path", None)
        _ = dataset_description.pop("_participants", None)
        dataset_description = clean_dict(
            dataset_description,
            skip_keys_to_manipulate=ManipulateKeysOption.ALL_KEYS_MANIPULATE,
        )
        write_json(dataset_description, output_path_dataset_description)

        for file in files_to_copy:
            if file is not None:
                copy_file(file, output_path / file.name)

        # write participants description to "participants.tsv"
        participants_dataframe = self.list_participants()
        participants_dataframe.to_csv(
            output_path / "participants.tsv", sep="\t", index=False
        )

        # write participants.json sidecar if columns are present
        output_path_participant_description = output_path / "participants.json"

        participant_description = {}
        columns = self._columns()
        for column in columns:
            column_dict = column.__dict__.copy()
            column_dict.pop("column_name")
            levels = column_dict.pop("_levels", None)

            participant_description[column.column_name] = column_dict

            if levels is not None:
                participant_description = add_levels_to_dict(
                    levels, column.column_name, participant_description
                )

        participant_description = clean_dict(
            participant_description,
            skip_keys_to_manipulate=ManipulateKeysOption.SKIP_TOP_LEVEL_MANIPULATE,
        )
        write_json(participant_description, output_path_participant_description)

        self.write_phenotype(output_path=output_path)

        # write each participant data
        for participant in self.participants.values():
            path = pathlib.Path(output_path) / participant.participant_id
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
            participant.write(path)

    def write_phenotype(self, output_path: os.PathLike | str) -> None:  # noqa: C901
        """
        Write phenotype measurement tables and sidecars.

        Parameters
        ----------
        output_path : os.PathLike | str
            Dataset output directory in which the ``phenotype`` folder is
            created.

        Returns
        -------
        None
            Files are written as side effects.

        See Also
        --------
        :py:func:`get_phenotypes_from_files`
            Inverse loader for phenotype measurement files.

        Notes
        -----
        Phenotype rows are grouped by measurement tool name and serialized to
        ``phenotype/<tool>.tsv`` with optional ``.json`` sidecars, matching the
        BIDS convention for participant-associated phenotype instruments.

        Examples
        --------
        >>> dataset.write_phenotype("out-dataset")
        """
        output_path = pathlib.Path(output_path)

        phenotypes = []
        measurement_tool_names = set()
        for participant in self.participants.values():
            if pht_list := participant.phenotype:
                phenotypes.append(pht_list)
                for pht in pht_list:
                    measurement_tool_names.add(pht.name)

        for toolname in measurement_tool_names:
            pht_tsv_path = output_path / "phenotype" / f"{toolname}.tsv"
            pht_json_path = output_path / "phenotype" / f"{toolname}.json"

            measurement_columns: Sequence[PhenotypeColumn] = []
            for phenotype_list in phenotypes:
                for phenotype in phenotype_list:
                    if phenotype.name == toolname and phenotype.columns:
                        measurement_columns = phenotype.columns
                        break

            # write phenotype json sidecar
            phenotype_description = {}
            for column in measurement_columns:
                column_dict = column.__dict__.copy()
                column_name = column_dict.pop("column_name")
                levels = column_dict.pop("_levels", None)

                phenotype_description[column_name] = column_dict

                if levels is not None:
                    phenotype_description = add_levels_to_dict(
                        levels, column_name, phenotype_description
                    )

            phenotype_description = clean_dict(
                phenotype_description,
                skip_keys_to_manipulate=ManipulateKeysOption.SKIP_TOP_LEVEL_MANIPULATE,
            )
            if not pht_json_path.parent.exists():
                pht_json_path.parent.mkdir(parents=True, exist_ok=True)
            write_json(phenotype_description, pht_json_path)

            # write phenotype tsv
            rows = []
            for phenotype_list in phenotypes:
                for phenotype in phenotype_list:
                    if phenotype.name == toolname:
                        row = {}
                        if phenotype.participant:
                            row["participant_id"] = phenotype.participant.participant_id
                        row.update(
                            {
                                key: value
                                for key, value in phenotype.__dict__.items()
                                if key not in COLUMNS_TO_REMOVE_FROM_TSV
                            }
                        )
                        rows.append(row)

            phenotype_df = pd.DataFrame(rows)
            phenotype_df.to_csv(pht_tsv_path, sep="\t", index=False)


def get_participants_from_files(
    dataset: Dataset,
    tsv_path: pathlib.Path | None,
    json_path: pathlib.Path | None,
) -> dict[str, Participant]:
    """
    Build participant objects from BIDS participant metadata files.

    Parameters
    ----------
    dataset : Dataset
        Parent dataset providing the root path and phenotype lookup context.
    tsv_path : pathlib.Path | None
        Path to ``participants.tsv`` if available.
    json_path : pathlib.Path | None
        Path to ``participants.json`` if available.

    Returns
    -------
    MutableSequence[Participant]
        Constructed :py:class:`~bidslab.common.specs_summary.Participant`
        objects.

    Raises
    ------
    FieldMissingError
        If a participants TSV row omits the required ``participant_id`` column.

    See Also
    --------
    :py:meth:`Dataset.participants`
        Lazy participant accessor that uses this helper.

    Notes
    -----
    If no participants TSV file is present, participant directories matching
    ``sub-*`` are used as a fallback discovery mechanism. Phenotype rows are
    attached by participant identifier after being loaded from
    :py:func:`get_phenotypes_from_files`.

    Examples
    --------
    >>> participants = get_participants_from_files(dataset, tsv_path, json_path)
    >>> participants[0].participant_id
    'sub-01'
    """
    participants: MutableSequence[Participant] = []
    columns = []

    measurement_tools = get_phenotypes_from_files(dataset)

    if json_path:
        column_data = parse_json_sidecar(json_path)
        column_data = clean_dict(
            column_data,
            skip_keys_to_manipulate=ManipulateKeysOption.SKIP_TOP_LEVEL_MANIPULATE,
            string_manipulation=to_snakecase,
        )
        for column_name, column_values in column_data.items():
            columns.append(Column(name=column_name, **column_values))

    if tsv_path:
        data = parse_descriptive_tsv(tsv_path)
        for participant in data:
            assert isinstance(participant, dict)
            participant_id = participant.get("participant_id")
            if participant_id is None:
                raise FieldMissingError(
                    "Field `participant_id` is required as column in participants.tsv"
                )
            add_object_to_sequence(
                entity_list=participants,
                entity_class=Participant,
                base_path=dataset.root / participant_id,
                columns=columns,
                dataset=dataset,
                phenotype=measurement_tools.get(participant_id, None),
                **participant,
            )
    else:
        dirs = dataset.root.iterdir()
        for directory in dirs:
            if directory.is_dir() and directory.name.startswith("sub-"):
                # TODO: Phenotype?
                add_object_to_sequence(
                    entity_list=participants,
                    entity_class=Participant,
                    base_path=dataset.root / directory.name,
                    participant_id=directory.name,
                    dataset=dataset,
                )
    participants_dict: dict[str, Participant] = {
        participant.participant_id: participant for participant in participants
    }
    return participants_dict


def get_phenotypes_from_files(
    dataset: Dataset,
) -> Mapping[str, Sequence[MeasurementTool]]:
    """
    Load phenotype measurement definitions grouped by participant.

    Parameters
    ----------
    dataset : Dataset
        Dataset whose :attr:`Dataset.phenotype_path` points to phenotype files.

    Returns
    -------
    Mapping[str, Sequence[MeasurementTool]]
        Mapping from participant identifier to sequences of
        :py:class:`~bidslab.common.specs_phenotype.MeasurementTool` objects.

    Raises
    ------
    FieldMissingError
        If a phenotype TSV row omits the required ``participant_id`` column.

    See Also
    --------
    :py:meth:`Dataset.write_phenotype`
        Serialize phenotype information back to disk.

    Notes
    -----
    Each phenotype TSV/JSON pair is interpreted as one measurement tool type as
    defined by the BIDS ``phenotype/`` convention. JSON sidecars are converted
    into :py:class:`PhenotypeColumn` metadata shared across all rows of the same
    tool.

    Examples
    --------
    >>> phenotypes = get_phenotypes_from_files(dataset)
    >>> phenotypes.get('sub-01', [])
    [<MeasurementTool ...>]
    """
    measurement_tools: dict[str, MutableSequence] = {}

    if pht_path := dataset.phenotype_path:
        files = pht_path.iterdir()
        measurement_tool_names = set()
        for file in files:
            measurement_tool_names.add(file.stem)
        for toolname in measurement_tool_names:
            measurement_columns = []
            pht_tsv_path, pht_json_path = get_tsv_json_files(pht_path, toolname)

            if pht_json_path:
                column_data = parse_json_sidecar(pht_json_path)
                for column_name, column_values in column_data.items():
                    measurement_columns.append(
                        PhenotypeColumn(name=column_name, **column_values)
                    )

            if pht_tsv_path:
                data = parse_descriptive_tsv(pht_tsv_path)
                for pht_participant in data:
                    assert isinstance(pht_participant, dict)
                    participant_id = pht_participant.pop("participant_id", None)
                    if participant_id is None:
                        raise FieldMissingError(
                            f"Field `participant_id` is required as column in "
                            f"phenotype/{toolname}.tsv"
                        )
                    if not measurement_tools.get(participant_id):
                        measurement_tools[participant_id] = []
                    measurement_tools[participant_id].append(
                        MeasurementTool(
                            name=toolname,
                            columns=measurement_columns,
                            **pht_participant,
                        )
                    )

    return measurement_tools
