#!/usr/bin/env python
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.

import sys
import os
DIR = os.path.abspath(os.path.normpath(os.path.join(__file__,
    '..', '..', '..', '..', '..', 'trytond')))
if os.path.isdir(DIR):
    sys.path.insert(0, os.path.dirname(DIR))

import datetime
import unittest
from decimal import Decimal
from dateutil.relativedelta import relativedelta
import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, DB_NAME, USER, CONTEXT, test_view,\
    test_depends
from trytond.exceptions import UserError
from trytond.transaction import Transaction


class TestCase(unittest.TestCase):
    '''
    Test module.
    '''

    def setUp(self):
        trytond.tests.test_tryton.install_module('stock_lot_expiry')
        self.company = POOL.get('company.company')
        self.location = POOL.get('stock.location')
        self.lot = POOL.get('stock.lot')
        self.move = POOL.get('stock.move')
        self.product = POOL.get('product.product')
        self.template = POOL.get('product.template')
        self.uom = POOL.get('product.uom')
        self.user = POOL.get('res.user')

    def test0005views(self):
        '''
        Test views.
        '''
        test_view('stock_lot_expiry')

    def test0006depends(self):
        '''
        Test depends.
        '''
        test_depends()

    def test0010_lot_on_change_product_and_expired(self):
        '''
        Test Lot.on_change_product() and Lot.expired.
        '''
        with Transaction().start(DB_NAME, USER,
                context=CONTEXT) as transaction:
            unit, = self.uom.search([('name', '=', 'Unit')])
            template, = self.template.create([{
                        'name': 'Test Lot.on_change_product() and Lot.expired',
                        'type': 'goods',
                        'consumable': True,
                        'list_price': Decimal(1),
                        'cost_price': Decimal(0),
                        'cost_price_method': 'fixed',
                        'default_uom': unit.id,
                        }])
            product, = self.product.create([{
                        'template': template.id,
                        'life_time': 20,
                        'expiry_time': 10,
                        'alert_time': 5,
                        }])
            lot, lot2, = self.lot.create([{
                        'number': '001',
                        'product': product.id,
                        }, {
                        'number': '002',
                        'product': product.id,
                        }])
            self.lot.write([lot], lot.on_change_product())

            today = datetime.date.today()
            self.assertEqual(lot.life_date, (today + relativedelta(days=20)))
            self.assertEqual(lot.expiry_date, (today + relativedelta(days=10)))
            self.assertEqual(lot.removal_date, None)
            self.assertEqual(lot.alert_date, (today + relativedelta(days=5)))

            self.assertEqual(lot2.expiry_date, None)

            with transaction.set_context(stock_move_date=today):
                self.assertEqual(self.lot(lot.id).expired, False)
                self.assertEqual(self.lot(lot2.id).expired, False)
            with transaction.set_context(
                    stock_move_date=(today + relativedelta(days=10))):
                self.assertEqual(self.lot(lot.id).expired, True)
                self.assertEqual(self.lot(lot2.id).expired, False)

    def test0020_move_check_allow_expired(self):
        '''
        Test Lot check_allow_expired.
        '''
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            company, = self.company.search([('party.name', '=', 'B2CK')])
            currency = company.currency
            self.user.write([self.user(USER)], {
                'main_company': company.id,
                'company': company.id,
                })

            unit, = self.uom.search([('name', '=', 'Unit')])
            template, = self.template.create([{
                        'name': 'Test Lot.on_change_product() and Lot.expired',
                        'type': 'goods',
                        'consumable': True,
                        'list_price': Decimal(1),
                        'cost_price': Decimal(0),
                        'cost_price_method': 'fixed',
                        'default_uom': unit.id,
                        }])
            product, = self.product.create([{
                        'template': template.id,
                        'life_time': 20,
                        'expiry_time': 10,
                        'alert_time': 5,
                        }])
            lot, lot2, = self.lot.create([{
                        'number': '001',
                        'product': product.id,
                        }, {
                        'number': '002',
                        'product': product.id,
                        }])
            self.lot.write([lot], lot.on_change_product())

            lost_found, = self.location.search([('type', '=', 'lost_found')])

            storage, = self.location.search([('code', '=', 'STO')])
            storage.allow_expired = True
            storage.save()

            expired_loc, not_allowed_expired_loc = self.location.create([{
                        'name': 'Expired Location',
                        'type': 'storage',
                        'expired': True,
                        'parent': storage.parent.id,
                        }, {
                        'name': 'Not Allowed Expired Location',
                        'type': 'storage',
                        'allow_expired': False,
                        'parent': storage.id,
                        }])
            self.assertEqual(expired_loc.allow_expired, True)

            today = datetime.date.today()
            expired_date = today + relativedelta(days=10)

            not_allowed_move, = self.move.create([{
                        'product': product.id,
                        'lot': lot.id,
                        'uom': unit.id,
                        'quantity': 1,
                        'from_location': lost_found.id,
                        'to_location': not_allowed_expired_loc.id,
                        'planned_date': today,
                        'company': company.id,
                        'unit_price': Decimal('1'),
                        'currency': currency.id,
                        }])
            not_allowed_move.effective_date = expired_date
            not_allowed_move.save()
            self.assertRaises(UserError, self.move.do, [not_allowed_move])

            moves = self.move.create([{
                        'product': product.id,
                        'lot': lot.id,
                        'uom': unit.id,
                        'quantity': 1,
                        'from_location': lost_found.id,
                        'to_location': not_allowed_expired_loc.id,
                        'planned_date': today,
                        'company': company.id,
                        'unit_price': Decimal('1'),
                        'currency': currency.id,
                        }, {
                        'product': product.id,
                        'lot': lot.id,
                        'uom': unit.id,
                        'quantity': 1,
                        'from_location': lost_found.id,
                        'to_location': storage.id,
                        'planned_date': expired_date,
                        'effective_date': expired_date,
                        'company': company.id,
                        'unit_price': Decimal('1'),
                        'currency': currency.id,
                        }, {
                        'product': product.id,
                        'lot': lot.id,
                        'uom': unit.id,
                        'quantity': 1,
                        'from_location': lost_found.id,
                        'to_location': expired_loc.id,
                        'planned_date': expired_date,
                        'effective_date': expired_date,
                        'company': company.id,
                        'unit_price': Decimal('1'),
                        'currency': currency.id,
                        }])
            self.move.do(moves)


def suite():
    suite = trytond.tests.test_tryton.suite()
    from trytond.modules.company.tests import test_company
    for test in test_company.suite():
        if test not in suite:
            suite.addTest(test)
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestCase))
    return suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
