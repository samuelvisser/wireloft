#!/usr/bin/env python3
"""
Test script to validate the new scheduling system.

Run this after starting the application to verify everything works.
"""

import sys
import os

# Add paths
sys.path.insert(0, 'server/motherboard/src')
sys.path.insert(0, 'server/backend/src')
sys.path.insert(0, 'server/config/src')

def test_imports():
    """Test that all imports work correctly."""
    print("Testing imports...")

    try:
        from wireloft_motherboard.scheduler.registry import task, on_cron, on_event
        print("✓ Registry decorators imported")
    except ImportError as e:
        print(f"✗ Failed to import registry: {e}")
        return False

    try:
        from wireloft_motherboard.events import emitters
        print("✓ Event emitters imported")
    except ImportError as e:
        print(f"✗ Failed to import emitters: {e}")
        return False

    try:
        from wireloft_motherboard.events.registry import get_wireloft_event_emitter
        print("✓ Event emitter registry imported")
    except ImportError as e:
        print(f"✗ Failed to import event registry: {e}")
        return False

    try:
        from wireloft_motherboard.db_utils import db_session
        print("✓ DB utils imported")
    except ImportError as e:
        print(f"✗ Failed to import db_utils: {e}")
        return False

    return True


def test_worker_imports():
    """Test that workers can be imported."""
    print("\nTesting worker imports...")

    try:
        from wireloft_motherboard.tasks.workers.fetch_new_episodes import fetch_new_episodes
        print("✓ fetch_new_episodes imported")

        # Check it has task metadata
        if hasattr(fetch_new_episodes, '_task_meta'):
            meta = fetch_new_episodes._task_meta
            print(f"  - Key: {meta.key}")
            print(f"  - Triggers: {len(meta.triggers)}")
            for idx, trigger in enumerate(meta.triggers):
                if trigger.trigger_type == 'cron':
                    print(f"    [{idx}] Cron: {trigger.cron}")
                elif trigger.trigger_type == 'event':
                    print(f"    [{idx}] Event: {trigger.event_name}")
        else:
            print("  ⚠ No task metadata found")
    except ImportError as e:
        print(f"✗ Failed to import fetch_new_episodes: {e}")
        return False

    try:
        from wireloft_motherboard.tasks.workers.download_profile_worker import download_profile_worker
        print("✓ download_profile_worker imported")
    except ImportError as e:
        print(f"✗ Failed to import download_profile_worker: {e}")
        return False

    return True


def test_registry():
    """Test that registry functions work."""
    print("\nTesting registry...")

    try:
        from wireloft_motherboard.scheduler.registry import all_triggers, all_definitions

        triggers = all_triggers()
        print(f"✓ Found {len(triggers)} tasks with triggers")

        for task_key, task_triggers in triggers.items():
            print(f"  - {task_key}: {len(task_triggers)} triggers")

        definitions = all_definitions()
        print(f"✓ Found {len(definitions)} task definitions")

    except Exception as e:
        print(f"✗ Registry test failed: {e}")
        return False

    return True


def test_decorator_usage():
    """Test that decorators work correctly."""
    print("\nTesting decorator usage...")

    try:
        from wireloft_motherboard.scheduler.registry import task, on_cron, on_event

        @task(
            key="test_task",
            title="Test Task",
            description="A test task",
        )
        @on_cron(cron="0 0 * * *")
        @on_event(event_name="test.event")
        async def test_task():
            pass

        if hasattr(test_task, '_task_meta'):
            meta = test_task._task_meta
            print(f"✓ Test task created: {meta.key}")
            print(f"  - Triggers: {len(meta.triggers)}")
            assert len(meta.triggers) == 2, "Should have 2 triggers"
            assert meta.triggers[0].trigger_type == 'cron'
            assert meta.triggers[1].trigger_type == 'event'
            print("✓ Decorator stacking works correctly")
        else:
            print("✗ Task metadata not found")
            return False

    except Exception as e:
        print(f"✗ Decorator test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


def main():
    print("=" * 60)
    print("WireLoft Scheduling System Test")
    print("=" * 60)

    all_passed = True

    # Run tests
    all_passed &= test_imports()
    all_passed &= test_worker_imports()
    all_passed &= test_registry()
    all_passed &= test_decorator_usage()

    print("\n" + "=" * 60)
    if all_passed:
        print("✓ All tests passed!")
        print("=" * 60)
        return 0
    else:
        print("✗ Some tests failed")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
