import unittest
import time

from opendm.display import (
    StageInfo,
    ETAEstimator,
    ProgressDisplay,
    _format_time,
    STAGE_DISPLAY_NAMES,
)


class TestFormatTime(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual(_format_time(5), '00:05')

    def test_minutes(self):
        self.assertEqual(_format_time(125), '02:05')

    def test_hours(self):
        self.assertEqual(_format_time(3661), '1:01:01')

    def test_zero(self):
        self.assertEqual(_format_time(0), '00:00')

    def test_none(self):
        self.assertEqual(_format_time(None), '--:--')

    def test_negative(self):
        self.assertEqual(_format_time(-5), '--:--')


class TestStageInfo(unittest.TestCase):
    def test_known_stage(self):
        s = StageInfo('opensfm')
        self.assertEqual(s.display_name, 'OpenSfM')
        self.assertEqual(s.status, 'pending')
        self.assertEqual(s.progress_pct, 0.0)

    def test_unknown_stage(self):
        s = StageInfo('custom_stage')
        self.assertEqual(s.display_name, 'custom_stage')


class TestETAEstimator(unittest.TestCase):
    def test_no_progress(self):
        eta = ETAEstimator()
        result = eta.estimate_remaining('opensfm', 10.0, 0.0)
        self.assertIsNone(result)

    def test_linear_extrapolation(self):
        eta = ETAEstimator()
        # 50% done in 10 seconds -> ~10 seconds remaining
        result = eta.estimate_remaining('opensfm', 10.0, 50.0)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 10.0, places=1)

    def test_quarter_done(self):
        eta = ETAEstimator()
        # 25% done in 5 seconds -> ~15 seconds remaining
        result = eta.estimate_remaining('opensfm', 5.0, 25.0)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 15.0, places=1)

    def test_nearly_done(self):
        eta = ETAEstimator()
        # 90% done in 90 seconds -> ~10 seconds remaining
        result = eta.estimate_remaining('opensfm', 90.0, 90.0)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 10.0, places=1)


class TestProgressDisplay(unittest.TestCase):
    def setUp(self):
        self.display = ProgressDisplay(
            stages_list=['dataset', 'opensfm', 'openmvs'],
            version='3.5.3',
            is_verbose=True,  # verbose mode so no rendering
        )

    def test_init(self):
        self.assertEqual(len(self.display.stages), 3)
        self.assertEqual(self.display.stages[0].name, 'dataset')
        self.assertEqual(self.display.stages[1].display_name, 'OpenSfM')
        self.assertTrue(self.display.is_verbose)

    def test_stage_lifecycle(self):
        self.display.stage_start('dataset')
        s = self.display._stage_map['dataset']
        self.assertEqual(s.status, 'running')
        self.assertIsNotNone(s.start_time)

        self.display.stage_end('dataset')
        self.assertEqual(s.status, 'done')
        self.assertGreater(s.elapsed, 0)

    def test_update_progress(self):
        self.display.stage_start('opensfm')
        self.display.update_progress('opensfm', 50.0, 'Matching: 25/50')
        s = self.display._stage_map['opensfm']
        self.assertEqual(s.progress_pct, 50.0)
        self.assertEqual(s.detail_line, 'Matching: 25/50')

    def test_progress_clamped(self):
        self.display.stage_start('opensfm')
        self.display.update_progress('opensfm', 150.0)
        s = self.display._stage_map['opensfm']
        self.assertEqual(s.progress_pct, 100.0)

    def test_set_image_count(self):
        self.display.set_image_count(150)
        self.assertEqual(self.display.image_count, 150)

    def test_unknown_stage_ignored(self):
        # Should not raise
        self.display.stage_start('nonexistent')
        self.display.stage_end('nonexistent')
        self.display.update_progress('nonexistent', 50.0)


class TestStageDisplayNames(unittest.TestCase):
    def test_all_stages_have_names(self):
        expected = [
            'dataset', 'split', 'merge', 'opensfm', 'openmvs',
            'odm_filterpoints', 'odm_meshing', 'mvs_texturing',
            'odm_georeferencing', 'odm_dem', 'odm_orthophoto',
            'odm_report', 'odm_postprocess',
        ]
        for stage in expected:
            self.assertIn(stage, STAGE_DISPLAY_NAMES)


if __name__ == '__main__':
    unittest.main()
