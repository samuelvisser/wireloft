from importlib import import_module


migration = import_module(
    "backend.db.alembic.versions.b7c3f1a9d2e4_migrate_filename_restriction_setting"
)


def test_filename_setting_migration_moves_legacy_true_to_windows():
    original = (
        "downloadSettings:\n"
        "  downloadRoot: /downloads\n"
        "  asciiOnlyFilenames: true\n"
    )

    migrated = migration._upgrade_config_text(original)

    assert "asciiOnlyFilenames" not in migrated
    assert "filenameRestrictionMode: windows" in migrated


def test_filename_setting_migration_moves_legacy_false_to_windows():
    original = (
        "downloadSettings:\n"
        "  ascii_only_filenames: false\n"
        "otherSetting: value\n"
    )

    migrated = migration._upgrade_config_text(original)

    assert "ascii_only_filenames" not in migrated
    assert "filenameRestrictionMode: windows" in migrated
    assert "otherSetting: value" in migrated


def test_filename_setting_migration_removes_legacy_key_when_new_mode_exists():
    original = (
        "downloadSettings:\n"
        "  asciiOnlyFilenames: true\n"
        "  filenameRestrictionMode: restricted\n"
    )

    migrated = migration._upgrade_config_text(original)

    assert "asciiOnlyFilenames" not in migrated
    assert migrated.count("filenameRestrictionMode") == 1
    assert "filenameRestrictionMode: restricted" in migrated


def test_filename_setting_downgrade_restores_old_default():
    original = (
        "downloadSettings:\n"
        "  filenameRestrictionMode: unrestricted\n"
    )

    downgraded = migration._downgrade_config_text(original)

    assert "filenameRestrictionMode" not in downgraded
    assert "asciiOnlyFilenames: true" in downgraded
