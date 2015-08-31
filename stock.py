# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from datetime import date, timedelta

from trytond.model import Workflow, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import And, Bool, Equal, Eval, If, Not
from trytond.transaction import Transaction

__all__ = ['Template', 'Lot', 'Location', 'Move']
__metaclass__ = PoolMeta


class Template:
    __name__ = 'product.template'

    life_time = fields.Integer('Life Time',
        help='The number of days before a lot may become dangerous and should '
        'not be consumed.')
    expiry_time = fields.Integer('Expiry Time',
        help='The number of days before a lot starts deteriorating without '
        'becoming dangerous.')
    removal_time = fields.Integer('Removal Time',
        help='The number of days before a lot should be removed.')
    alert_time = fields.Integer('Alert Time',
        help='The number of days after which an alert should be notified '
        'about the lot.')


class Lot:
    __name__ = 'stock.lot'

    life_date = fields.Date('End of Life Date',
        help='The date on which the lot may become dangerous and should not '
        'be consumed.')
    expiry_date = fields.Date('Expiry Date',
        help='The date on which the lot starts deteriorating without becoming '
        'dangerous.')
    removal_date = fields.Date('Removal Date',
        help='The date on which the lot should be removed.')
    alert_date = fields.Date('Alert Date',
        help='The date on which an alert should be notified about the lot.')
    expired = fields.Function(fields.Boolean('Expired'),
        'get_expired', searcher='search_expired')

    @classmethod
    def __setup__(cls):
        super(Lot, cls).__setup__()
        cls._error_messages.update({
                'Expired': 'Expired',
                })

    def get_rec_name(self, name):
        rec_name = super(Lot, self).get_rec_name(name)
        if self.expired:
            rec_name += ' (%s)' % self.raise_user_error('Expired',
                raise_exception=False)
        return rec_name

    @fields.depends('product', 'life_date', 'expiry_date', 'removal_date',
        'alert_date')
    def on_change_product(self):
        try:
            super(Lot, self).on_change_product()
        except AttributeError:
            pass

        if not self.product:
            return

        for fname in ('life_date', 'expiry_date', 'removal_date',
                'alert_date'):
            product_field = fname.replace('date', 'time')
            margin = getattr(self.product.template, product_field)
            value = (margin and date.today() + timedelta(days=margin))
            setattr(self, fname, value)

    def get_expired(self, name):
        pool = Pool()
        Date = pool.get('ir.date')

        if not self.expiry_date:
            return False

        context = Transaction().context
        date = Date.today()
        if context.get('stock_move_date'):
            date = context['stock_move_date']
        elif context.get('stock_date_end'):
            date = context['stock_date_end']
        return self.expiry_date <= date

    @classmethod
    def search_expired(cls, name, domain=None):
        pool = Pool()
        Date = pool.get('ir.date')

        if not domain:
            return []

        context = Transaction().context
        date = Date.today()
        if context.get('stock_move_date'):
            date = context['stock_move_date']
        elif context.get('stock_date_end'):
            date = context['stock_date_end']
        _, op, operand = domain
        search_expired = (op == '=' and operand
            or op == '!=' and not operand)
        if search_expired:
            return [
                ('expiry_date', '!=', None),
                ('expiry_date', '<=', date),
                ]
        else:
            return [
                'OR', [
                    ('expiry_date', '=', None),
                    ], [
                    ('expiry_date', '>', date),
                    ]]


class Location:
    __name__ = 'stock.location'

    expired = fields.Boolean('Expired Products\' Location',
        help='This option identifies this location as a container for expired '
        'products (provably it is a temporal location until the product is '
        'returned or removed).\n'
        'Take care that if you set this location as a child of the Storage '
        'location of a Warehouse, the products in this location will be '
        'computed as available stock.')
    allow_expired = fields.Boolean('Allow Expired', states={
            'invisible': Eval('expired', False),
            }, depends=['expired'],
        help='Check this option to allow move expired lots to this location.')

    @fields.depends('expired', 'allow_expired')
    def on_change_expired(self):
        if self.expired:
            self.allow_expired = True

    @classmethod
    def create(cls, vlist):
        for vals in vlist:
            if vals.get('expired'):
                vals['allow_expired'] = True
        return super(Location, cls).create(vlist)

    @classmethod
    def write(cls, *args):
        actions = iter(args)
        args = []
        for locations, values in zip(actions, actions):
            if values.get('expired'):
                values['allow_expired'] = True
            args.extend((locations, values))
        super(Location, cls).write(*args)


class Move:
    __name__ = 'stock.move'

    to_location_allow_expired = fields.Function(
        fields.Boolean('Destination Allow Expired'),
        'on_change_with_to_location_allow_expired')

    @classmethod
    def __setup__(cls):
        super(Move, cls).__setup__()
        cls.lot.domain.append(
            If(And(Equal(Eval('state', 'draft'), 'draft'),
                    Not(Bool(Eval('to_location_allow_expired', True)))),
                ('expired', '=', False),
                ()),
            )
        if not cls.lot.context:
            cls.lot.context = {}
        cls.lot.context['stock_move_date'] = If(
            Bool(Eval('effective_date', False)),
            Eval('effective_date'),
            Eval('planned_date'))
        for fname in ('state', 'to_location_allow_expired', 'effective_date',
                'planned_date'):
            if fname not in cls.lot.depends:
                cls.lot.depends.append(fname)
        cls._error_messages.update({
            'expired_lot_invalid_destination': ('You are trying to do the '
                'Stock Move "%(move)s" but its Lot "%(lot)s" is expired and '
                'the Destination Location "%(to_location)s" doesn\'t accept '
                'expired lots.'),
            })

    @fields.depends('to_location')
    def on_change_with_to_location_allow_expired(self, name=None):
        return self.to_location and self.to_location.allow_expired or False

    @classmethod
    @ModelView.button
    @Workflow.transition('done')
    def do(cls, moves):
        for move in moves:
            move.check_allow_lot_expired()
        super(Move, cls).do(moves)

    def check_allow_lot_expired(self):
        if self.to_location.allow_expired or not self.lot:
            return

        error = False
        with Transaction().set_context(stock_move_date=self.effective_date):
            error = not self.to_location.allow_expired and self.lot.expired
        if error:
            self.raise_user_error('expired_lot_invalid_destination', {
                    'move': self.rec_name,
                    'lot': self.lot.rec_name,
                    'to_location': self.to_location.rec_name,
                    })
