"""Guard published AETHRON pricing against inconsistent release or website updates."""

import unittest

from scripts.check_commercial_pricing import check


class CommercialPricingTests(unittest.TestCase):
    def test_public_pricing_contracts_and_links(self):
        check()


if __name__ == "__main__":
    unittest.main()
