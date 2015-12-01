# This file is part of the stock_lot_expiry module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import unittest
import trytond.tests.test_tryton
from trytond.tests.test_tryton import ModuleTestCase


class StockLotExpiryTestCase(ModuleTestCase):
    'Test Stock Lot Expiry module'
    module = 'stock_lot_expiry'


def suite():
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
        StockLotExpiryTestCase))
    return suite