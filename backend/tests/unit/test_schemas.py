import uuid

import pytest
from pydantic import ValidationError

from grudge_backend.schemas.automaton import AutomatonCreate, AutomatonUpdate
from grudge_backend.schemas.folder import FolderCreate, FolderUpdate
from grudge_backend.schemas.version import VersionCreate, VersionUpdate


def test_folder_create_requires_name():
    with pytest.raises(ValidationError):
        FolderCreate(name="")


def test_folder_create_parent_id_optional():
    folder = FolderCreate(name="My Folder")
    assert folder.parent_id is None


def test_folder_update_exclude_unset_distinguishes_omitted_from_null():
    # omitted entirely -> not present in exclude_unset dump
    update_omitted = FolderUpdate(name="new name")
    dumped_omitted = update_omitted.model_dump(exclude_unset=True)
    assert "parent_id" not in dumped_omitted

    # explicitly set to null -> present, with value None (move to root)
    update_explicit_null = FolderUpdate(name="new name", parent_id=None)
    dumped_explicit = update_explicit_null.model_dump(exclude_unset=True)
    assert "parent_id" in dumped_explicit
    assert dumped_explicit["parent_id"] is None


def test_automaton_create_requires_name():
    with pytest.raises(ValidationError):
        AutomatonCreate(name="")


def test_automaton_create_code_optional():
    automaton = AutomatonCreate(name="Bot")
    assert automaton.code is None


def test_automaton_update_partial_fields_all_optional():
    update = AutomatonUpdate()
    assert update.model_dump(exclude_unset=True) == {}


def test_version_create_allows_omitted_code_and_name():
    version = VersionCreate()
    assert version.name is None
    assert version.code is None


def test_version_update_rejects_blank_name():
    with pytest.raises(ValidationError):
        VersionUpdate(name="")


def test_folder_create_accepts_uuid_parent_id():
    parent_id = uuid.uuid4()
    folder = FolderCreate(name="Child", parent_id=parent_id)
    assert folder.parent_id == parent_id
