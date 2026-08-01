import unittest

import aic51.resources as resources


class ResourceImportTests(unittest.TestCase):
    def test_resource_package_imports_without_transnet_submodule(self):
        self.assertTrue(hasattr(resources, "LAYOUT_FILE_PATH"))
        self.assertTrue(resources.TransNetV2 is None or callable(resources.TransNetV2))


if __name__ == "__main__":
    unittest.main()
