"""Test that all modules can be imported correctly."""

import unittest

class TestImports(unittest.TestCase):
    """Test that all modules can be imported correctly."""
    
    def test_import_package(self):
        """Test that the package can be imported."""
        import dailywire_downloader
        self.assertIsNotNone(dailywire_downloader)
        self.assertEqual(dailywire_downloader.__version__, "0.1.0")
    
    def test_import_downloader(self):
        """Test that the downloader module can be imported."""
        from dailywire_downloader import downloader
        self.assertIsNotNone(downloader)
    
    def test_import_nfo(self):
        """Test that the nfo module can be imported."""
        from dailywire_downloader import nfo
        self.assertIsNotNone(nfo)
    
    def test_import_cli(self):
        """Test that the cli module can be imported."""
        from dailywire_downloader import cli
        self.assertIsNotNone(cli)

if __name__ == "__main__":
    unittest.main()