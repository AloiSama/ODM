import unittest
from opendm.output_parsers import (
    parse_openmvs_densify,
    parse_poisson_recon,
    parse_texrecon,
    parse_orthophoto,
    parse_opensfm,
    parse_dem,
    parse_generic_pct,
    parse_line,
)


class TestOpenMVSParser(unittest.TestCase):
    def test_fraction_pattern(self):
        result = parse_openmvs_densify("Estimate depth-map for image 50 / 150 (33%)")
        self.assertIsNotNone(result)
        pct, detail = result
        self.assertAlmostEqual(pct, 33.3, places=0)
        self.assertIn('50/150', detail)

    def test_percentage_pattern(self):
        result = parse_openmvs_densify("Densified 67%")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 67.0)

    def test_no_match(self):
        result = parse_openmvs_densify("Loading scene from file")
        self.assertIsNone(result)


class TestPoissonReconParser(unittest.TestCase):
    def test_depth_level(self):
        result = parse_poisson_recon("Depth[ 8/10]")
        self.assertIsNotNone(result)
        pct, detail = result
        self.assertAlmostEqual(pct, 80.0, places=0)
        self.assertIn('8/10', detail)

    def test_no_match(self):
        result = parse_poisson_recon("Running Screened Poisson Reconstruction")
        self.assertIsNone(result)


class TestTexreconParser(unittest.TestCase):
    def test_view_count(self):
        result = parse_texrecon("Generating texture views (75/150)")
        self.assertIsNotNone(result)
        pct, detail = result
        self.assertAlmostEqual(pct, 50.0, places=0)
        self.assertIn('75/150', detail)

    def test_no_match(self):
        result = parse_texrecon("Loading mesh")
        self.assertIsNone(result)


class TestOrthophotoParser(unittest.TestCase):
    def test_percentage(self):
        result = parse_orthophoto("Writing: 45%")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 45.0)

    def test_no_match(self):
        result = parse_orthophoto("Loading textures")
        self.assertIsNone(result)


class TestOpenSfMParser(unittest.TestCase):
    def test_matching(self):
        result = parse_opensfm("Matching image 30 / 100")
        self.assertIsNotNone(result)
        pct, detail = result
        self.assertAlmostEqual(pct, 30.0, places=0)
        self.assertIn('30/100', detail)

    def test_detecting(self):
        result = parse_opensfm("Detecting features in image 10 / 50")
        self.assertIsNotNone(result)
        pct, detail = result
        self.assertAlmostEqual(pct, 20.0, places=0)

    def test_undistorting(self):
        result = parse_opensfm("Undistorting image 5 / 20")
        self.assertIsNotNone(result)
        pct, detail = result
        self.assertAlmostEqual(pct, 25.0, places=0)

    def test_no_match(self):
        result = parse_opensfm("Loading camera models")
        self.assertIsNone(result)


class TestGenericPctParser(unittest.TestCase):
    def test_valid_percentage(self):
        result = parse_generic_pct("Progress: 50%")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 50.0)

    def test_zero_ignored(self):
        result = parse_generic_pct("0% done")
        self.assertIsNone(result)

    def test_over_100_ignored(self):
        result = parse_generic_pct("200% overbudget")
        self.assertIsNone(result)

    def test_no_match(self):
        result = parse_generic_pct("no numbers here")
        self.assertIsNone(result)


class TestParseLineDispatch(unittest.TestCase):
    def test_routes_to_openmvs(self):
        result = parse_line("Estimate depth-map for image 5 / 10", 'openmvs')
        self.assertIsNotNone(result)

    def test_routes_to_opensfm(self):
        result = parse_line("Matching image 3 / 10", 'opensfm')
        self.assertIsNotNone(result)

    def test_falls_back_to_generic(self):
        result = parse_line("Progress: 42%", 'odm_filterpoints')
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 42.0)

    def test_unknown_stage_generic(self):
        result = parse_line("75% complete", 'unknown_stage')
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 75.0)

    def test_no_match_at_all(self):
        result = parse_line("just a log message", 'openmvs')
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
