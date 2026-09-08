import unittest

from artifact_check import compiler_matches, ev3_package_name


class CompilerFactTests(unittest.TestCase):
    def test_debian_version_parentheses_match_compact_lock(self):
        facts="arm-linux-gnueabi-g++ (Debian 6.3.0-18) 6.3.0 20170516 | abc  /usr/bin/arm-linux-gnueabi-g++"
        self.assertTrue(compiler_matches("arm-linux-gnueabi-g++ 6.3.0-18",facts))

    def test_wrong_executable_or_package_revision_rejected(self):
        facts="arm-linux-gnueabi-g++ (Debian 6.3.0-17) 6.3.0 20170516"
        self.assertFalse(compiler_matches("arm-linux-gnueabi-g++ 6.3.0-18",facts))
        self.assertFalse(compiler_matches("arm-linux-gnueabihf-g++ 6.3.0-17",facts))


class PackageNameTests(unittest.TestCase):
    def test_content_addressed_package_name(self):
        self.assertEqual(ev3_package_name("abc"),"phantom-abc.tar.gz")


if __name__=="__main__":unittest.main()
