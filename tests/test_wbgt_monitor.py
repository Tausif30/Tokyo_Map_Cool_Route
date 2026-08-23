import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from WBGT_Monitor import fetch_latest_reading


class FetchLatestReadingTests(unittest.TestCase):
    @patch("WBGT_Monitor.requests.get")
    def test_api_window_is_always_converted_to_tokyo_time(self, mock_get):
        response = Mock()
        response.json.return_value = {
            "status": "success",
            "data": [
                {
                    "wbgt_date": "2026/08/23 15:00:00",
                    "wbgt_class": 1,
                    "wbgt_WI": "4.0",
                    "wbgt_WO": "26.4",
                }
            ],
        }
        mock_get.return_value = response

        result = fetch_latest_reading(
            now=datetime(2026, 8, 23, 6, 0, tzinfo=timezone.utc)
        )

        params = mock_get.call_args.kwargs["params"]
        self.assertIn(("date_to", "20260823150000"), params)
        self.assertIn(("date_from", "20260823090000"), params)
        self.assertEqual(result["observed_at"], "2026/08/23 15:00:00")
        self.assertEqual(result["wbgt_c"], 26.4)


if __name__ == "__main__":
    unittest.main()
