#!/usr/bin/env python
try:
    from lxml import etree
except ImportError:
    try:
        from xml.etree import cElementTree as etree  # Python 2.5 or later
    except ImportError:
        from xml.etree import ElementTree as etree   # Python 2.5 or later

import gzip
from datetime import date, datetime
import calendar

def nstag(tag):
    prefix, name = tag.split(':')
    return '{http://www.gnucash.org/XML/%s}%s' % (prefix, name)

def _find(elm, tag):
    return elm.find(nstag(tag))
def _findall(elm, tag):
    return elm.findall(nstag(tag))
def _findtext(elm, tag):
    return elm.findtext(nstag(tag))

class ElementWrapper(object):
    """An element wrapper class."""
    def __init__(self, element):
        self.element = element

    def _find(self, tag):
        return self.element.find(nstag(tag))
    def _findall(self, tag):
        return self.element.findall(nstag(tag))
    def _findtext(self, tag):
        return self.element.findtext(nstag(tag))

class Commodity(ElementWrapper):
    """A commodity class."""
    def __init__(self, element):
        ElementWrapper.__init__(self, element)
        if element is not None: self.convert(element)

    def convert(self, element):
        self.space = self._findtext('cmdty:space')
        self.id = self._findtext('cmdty:id')
        self.quote_source = self._findtext('cmdty:quote_source')

class Account(ElementWrapper):
    """An account class"""
    def __init__(self, book, element=None):
        ElementWrapper.__init__(self, element)
        self.book = book
        self.children = []
        self.splits = []
        if element is not None: self.convert(element)

    def __lt__(self, other):
        return self.name < other.name

    def convert(self, element):
        self.name = self._findtext('act:name')
        self.id = self._findtext('act:id')
        self.type = self._findtext('act:type')
        self.description = self._findtext('act:description')
        self.pid = self._findtext('act:parent')

    def __str__(self):
        return ': '.join([self.id, self.name])

    def _totree(self, indent=0):
        buf = [self.name]
        for child in self.children:
            buf.append('\n|')
            if indent > 0:
                buf.append(' ' * (indent - 1) + '|-')
            else:
                buf.append('-')
            buf.append(child._totree(indent + 2))
        return ''.join(buf)

    def totree(self):
        """Return the string of an account tree."""
        return self._totree()

    def insert(self, entity):
        if type(entity) is Account:
            self.children.append(entity)
        elif type(entity) is Split:
            self.splits.append(entity)

    def remove(self, entity):
        if type(entity) is Account:
            self.children.remove(entity)
        elif type(entity) is Split:
            self.splits.remove(entity)

    def descendants(self):
        """Gets the descendants of an account."""
        acts = []
        for act in sorted(self.children):
            acts.append(act)
            if act.children:
                acts.extend(act.descendants())
        return acts

    def balance(self, start=date.min, end=date.max):
        # In liability, equity and income accounts, credits increase the
        # balance and debits decrease the balance.
        bln = sum([split.value for split in self.splits
                   if start <= split.date() and split.date() <= end])
        if bln != 0 and self.type in set(['LIABILITY', 'EQUITY', 'INCOME']):
            bln *= -1
        return bln

class Split(ElementWrapper):
    """A split classs"""
    def __init__(self, element=None):
        ElementWrapper.__init__(self, element)
        self.account = None
        self.transaction = None
        if element is not None: self.convert(element)

    def __lt__(self, other):
        return self.transaction.date_posted < other.transaction.date_posted

    def convert(self, element):
        self.id = self._findtext('split:id')
        a, b = self._findtext('split:value').split('/')
        self.value = float(a)/float(b)
        self.quantity = self._findtext('split:quantity')
        self.accountid = self._findtext('split:account')

    def date(self):
        return self.transaction.date_posted.date()

class Transaction(ElementWrapper):
    """A transaction class"""
    def __init__(self, element=None):
        ElementWrapper.__init__(self, element)
        if element is not None: self.convert(element)

    def __lt__(self, other):
        return self.date_posted < other.date_posted

    def convert(self, element):
        self.id = self._findtext('trn:id')
        self.currency = self._find('trn:currency')

        date_format = '%Y-%m-%d %H:%M:%S'
        date_string = _findtext(self._find('trn:date-posted'), 'ts:date')
        self.date_posted = datetime.strptime(date_string[:19], date_format)
        date_string = _findtext(self._find('trn:date-entered'), 'ts:date')
        self.date_entered = datetime.strptime(date_string[:19], date_format)

        self.description = self._findtext('trn:description')
        splits_elms = _findall(self._find('trn:splits'), 'trn:split')
        self.splits = self._mksplits(splits_elms)

    def __str__(self):
        s = ['{0}, {1}'.format(self.date_posted.strftime('%Y-%m-%d'),
                              self.description)]
        for sp in self.splits:
            name = sp.account and sp.account.name or sp.accountid
            s.append('  {0} {1}'.format(name, sp.value))
        return '\n'.join(s)

    def _mksplits(self, elms):
        slist = []
        for elm in elms:
            split = Split(elm)
            slist.append(split)
        return slist

class Book(ElementWrapper):
    """A book class"""
    def __init__(self, element=None):
        if type(element) == str:
            tree = etree.parse(gzip.GzipFile(element))
            element = _find(tree.getroot(), 'gnc:book')
        ElementWrapper.__init__(self, element)
        if element is not None: self.convert(element)

    def convert(self, element):
        self.id = self._findtext('book:id')
        self.commodity = Commodity(self._find('gnc:commodity'))
        actelms = self._findall('gnc:account')
        self.accounts, self.actdic = self._mkaccounts(actelms)
        trnelms = self._findall('gnc:transaction')
        self.transactions, self.trndic = self._mktransactions(trnelms)

    def __str__(self):
        return self.summary()

    def summary(self):
        return 'Summary: {0} accounts and {1} transactions'.format(
            len(self.accounts), len(self.transactions))

    def _mkaccounts(self, elms):
        actlist = []
        actdic = {}
        for elm in elms:
            act = Account(self, elm)
            actlist.append(act)
            actdic[act.id] = act
            pid = act.pid
            if pid is None:
                pass
            else:
                parent = actdic[pid]
                parent.children.append(act)
        return actlist, actdic

    def _mktransactions(self, elms):
        trnlist = []
        trndic = {}
        for elm in elms:
            trn = Transaction(elm)
            for split in trn.splits:
                act = self.actdic[split.accountid]
                act.insert(split)
                split.account = act
                split.transaction = trn
            trnlist.append(trn)
            trndic[trn.id] = trn
        return trnlist, trndic

    def getrootact(self, type=None):
        """Gets the root account"""
        # assume the first element of the account list is a root.
        rootact = self.accounts[0]
        if type is not None:
            # assume the root account has 5 fundamental type accounts as its
            # children.
            for act in rootact.children:
                if act.type == type:
                    return act
        return rootact

    def findact(self, name):
        """Find an account with the name."""
        for act in self.accounts:
            if act.name == name:
                return act
        return None

    def printacttree(self, name=None):
        """Print an account tree."""
        if name is None:
            print self.getrootact().totree()
        else:
            try:
                print self.findact(name).totree()
            except:
                pass

    def first_transaction(self):
        return sorted(self.transactions)[0]

    def last_transaction(self):
        return sorted(self.transactions)[-1]

    def account_ledger(self, name, start=date.min, end=date.max):
        """Returns an account register ledger."""
        act = self.findact(name)
        return act and AccountLedger(act, start, end)

    def balance_sheet(self, view='annual'):
        """Returns a balance sheet."""
        # FIXME!
        endings = [date(2011,12,31), date(2010,12,31), date(2009,12,31)]
        return BalanceSheet(self, endings)

    def income_stm(self, start=date.min, end=date.max):
        """Returns an income statement over a given period."""
        return IncomeStm(self, [(start, end)])

    def monthly_income_stm(self, year=date.max.year):
        """Returns a monthly income statement."""
        if year == date.max.year:
            year = self.last_transaction().date_posted.year
        periods = [(first_date_of_month(year, m), last_date_of_month(year, m))
                   for m in range(1, 13)]  # for each month of the year
        return IncomeStm(self, periods)

    def monthly_income_stms(self):
        """Returns a list of monthly income statements on each year."""
        first = self.first_transaction().date_posted.year
        last = self.last_transaction().date_posted.year
        years = range(first, last + 1)
        years.reverse()
        
        stms = []
        for year in years:
            stms.append((year, self.monthly_income_stm(year)))
        return stms

class AccountLedger(object):
    """An account ledger"""
    def __init__(self, account, start=date.min, end=date.max):
        self.account = account
        self.splits = [split for split in account.splits
                       if start <= split.date() and split.date() <= end]
        self.splits.sort()

    def __str__(self):
        s = []
        balance = 0
        for split in self.splits:
            trn = split.transaction
            balance += split.value
            s.append('%s, %s, %.2f, %.2f' % (
                trn.date_posted.date(), trn.description, split.value, balance))
        return '\n'.join(s)

class BalanceSheet(object):
    """A balance sheet"""
    def __init__(self, book, endings):
        self.endings = endings
        self.assets = [(ac, []) for ac in
                       book.getrootact('ASSET').descendants()]
        self.liabilities = [(ac, []) for ac in
                            book.getrootact('LIABILITY').descendants()]
        self.equity = [(ac, []) for ac in
                       book.getrootact('EQUITY').descendants()]
        self.total = {'assets': [], 'liabilities': [], 'equity': []}

        # Get each balance of the accounts of assets, liabilities and equity.
        for ending in endings:
            total = 0
            for ac, balances in self.assets:
                bln = ac.balance(end=ending)
                balances.append(bln)
                total += bln
            self.total['assets'].append(total)

            total = 0
            for ac, balances in self.liabilities:
                bln = ac.balance(end=ending)
                balances.append(bln)
                total += bln
            self.total['liabilities'].append(total)

            total = 0
            for ac, balances in self.equity:
                bln = ac.balance(end=ending)
                balances.append(bln)
                total += bln
            self.total['equity'].append(total)

    def __str__(self):
        return self.tocsv()

    def tocsv(self):
        s = ['Period Endings, ' + ', '.join([str(d) for d in self.endings])]

        s.append('- Assets:')
        for act, balances in self.assets:
            buf = ['%.2f' % b for b in balances]
            s.append('%s, %s' % (act.name, ', '.join(buf)))
        buf = ['%.2f' % b for b in self.total['assets']]
        s.append('Total Assets, ' + ', '.join(buf))

        s.append('- Liabilities:')
        for act, balances in self.liabilities:
            buf = ['%.2f' % b for b in balances]
            s.append('%s, %s' % (act.name, ', '.join(buf)))
        buf = ['%.2f' % b for b in self.total['liabilities']]
        s.append('Total Liabilities, ' + ', '.join(buf))

        s.append('- Equity:')
        for act, balances in self.equity:
            buf = ['%.2f' % b for b in balances]
            s.append('%s, %s' % (act.name, ', '.join(buf)))
        buf = ['%.2f' % b for b in self.total['equity']]
        s.append('Total Equity, ' + ', '.join(buf))

        return '\n'.join(s)

    def tohtml(self, caption=None):
        colspan = len(self.endings) + 1
        s = ['<table>']
        if caption:
            s.append('  <caption>%s</caption>' % caption)
        s.append('  <thead>')
        buf = ['<th>%s</th>' % str(d) for d in self.endings]
        s.append('    <tr><th>Period Ending</th>' + ''.join(buf) + '</tr>')
        s.append('  </thead>')
        s.append('  <tbody>')

        s.append('    <tr><td colspan="%d">Assets</td></tr>' % colspan)
        for act, balances in self.assets:
            buf = ['<td>%.2f</td>' % b for b in balances]
            s.append('    <tr><td>%s</td>%s</tr>' % (act.name, ''.join(buf)))
        buf = ['<td>%.2f</td>' % t for t in self.total['assets']]
        s.append('    <tr><td><b>Total Assets</b></td>%s</tr>' % ''.join(buf))
        s.append('    <tr><td colspan="%d"></td></tr>' % colspan)

        s.append('    <tr><td colspan="%d">Liabilities</td></tr>' % colspan)
        for act, balances in self.liabilities:
            buf = ['<td>%.2f</td>' % b for b in balances]
            s.append('    <tr><td>%s</td>%s</tr>' % (act.name, ''.join(buf)))
        buf = ['<td>%.2f</td>' % t for t in self.total['liabilities']]
        s.append('    <tr><td><b>Total Liabilities</b></td>%s</tr>' %
                 ''.join(buf))
        s.append('    <tr><td colspan="%d"></td></tr>' % colspan)

        s.append('    <tr><td colspan="%d">Equity</td></tr>' % colspan)
        for act, balances in self.equity:
            buf = ['<td>%.2f</td>' % b for b in balances]
            s.append('    <tr><td>%s</td>%s</tr>' % (act.name, ''.join(buf)))
        buf = ['<td>%.2f</td>' % t for t in self.total['liabilities']]
        s.append('    <tr><td><b>Total Equity</b></td>%s</tr>' % ''.join(buf))
        s.append('  </tbody>')
        s.append('</table>')
        return '\n'.join(s)

def first_date_of_month(year, month):
    return date(year, month, 1)

def last_date_of_month(year, month):
    return date(year, month, calendar.monthrange(year, month)[1])

monthnames = ['January', 'February', 'March', 'April', 'May', 'June',
              'July','August', 'September', 'October', 'November', 'December']

class IncomeStm(object):
    """An income statement"""
    def __init__(self, book, periods, view='monthly'):
        self.periods = periods
        self.incomes = [(ac, []) for ac in
                        book.getrootact('INCOME').descendants()]
        self.expenses = [(ac, []) for ac in
                         book.getrootact('EXPENSE').descendants()]
        self.total = {'incomes': [], 'expenses': []}

        # Get each balance of the income and expense accounts
        for beginning, ending in periods:
            total = 0
            for ac, balances in self.incomes:
                bln = ac.balance(beginning, ending)
                balances.append(bln)
                total += bln
            self.total['incomes'].append(total)

            total = 0
            for ac, balances in self.expenses:
                bln = ac.balance(beginning, ending)
                balances.append(bln)
                total += bln
            self.total['expenses'].append(total)

        # Filter out accounts containing only zero balances
        self.incomes = filter(lambda p: sum(p[1]) != 0, self.incomes)
        self.expenses = filter(lambda p: sum(p[1]) != 0, self.expenses)

    def __str__(self):
        return self.tocsv()

    def tocsv(self):
        s = []
        s.append('Incomes:')
        for act, balances in self.incomes:
            buf = ['%.2f' % b for b in balances]
            s.append('%s, %s' % (act.name, ', '.join(buf)))
        buf = ['%.2f' % t for t in self.total['incomes']]
        s.append('Total Income, ' + ', '.join(buf) + '\n')

        s.append('Expenses:')
        for act, balances in self.expenses:
            buf = ['%.2f' % b for b in balances]
            s.append('%s, %s' % (act.name, ', '.join(buf)))
        buf = ['%.2f' % t for t in self.total['expenses']]
        s.append('Total Expenses, ' + ', '.join(buf) + '\n')

        buf = ['%.2f' % (i - e) for i, e
               in zip(self.total['incomes'], self.total['expenses'])]
        s.append('Net Income, ' + ', '.join(buf))
        return '\n'.join(s)

    def tohtml(self, caption=None):
        ncols = len(self.periods) + 1
        s = ['<table>']
        if caption:
            s.append('  <caption>%s</caption>' % caption)
        s.append('  <thead>')
        buf = ['<th>%s</th>' % m for m in monthnames]
        s.append('    <tr><th>Period Ending</th>%s</tr>' % ''.join(buf))
        s.append('  </thead>')

        s.append('  <tbody>')
        s.append('    <tr><td colspan="%d">Incomes</td></tr>' % ncols)
        for act, balances in self.incomes:
            buf = ['<td>%.2f</td>' % b for b in balances]
            s.append('    <tr><td>%s</td>%s</tr>' % (act.name, ''.join(buf)))
        buf = ['<td>%.2f</td>' % t for t in self.total['incomes']]
        s.append('    <tr><td><b>Total Incomes</b></td>%s</tr>' % ''.join(buf))
        s.append('    <tr><td colspan="%d"></td></tr>' % ncols)

        s.append('    <tr><td colspan="%d">Expenses</td></tr>' % ncols)
        for act, balances in self.expenses:
            buf = ['<td>%.2f</td>' % b for b in balances]
            s.append('    <tr><td>%s</td>%s</tr>' % (act.name, ''.join(buf)))
        buf = ['<td>%.2f</td>' % t for t in self.total['expenses']]
        s.append('    <tr><td><b>Total Expenses</b></td>%s</tr>' % ''.join(buf))
        s.append('    <tr><td colspan="%d"></td></tr>' % ncols)

        buf = ['<td>%.2f</td>' % (i - e) for i, e in
               zip(self.total['incomes'], self.total['expenses'])]
        s.append('    <tr><td><b>Net Income</b></td>%s</tr>' % ''.join(buf))
        s.append('  </tbody>')
        s.append('</table>')
        return '\n'.join(s)

def gncopen(source):
    """Open a GnuCash file, parse it, and return the first book."""
    gzipfile = None
    if type(source) is str:
        gzipfile = gzip.GzipFile(source)
    else:
        gzipfile = gzip.GzipFile(fileobj=source)
    tree = etree.parse(gzipfile)
    book = _find(tree.getroot(), 'gnc:book')
    return Book(book)

def main():
    import sys
    from optparse import OptionParser

    parser = OptionParser(usage="Usage: %prog <filename> [year [month]]")
    options, args = parser.parse_args()
    if len(args) < 1:
        parser.error("no Gnucash file")

    try:
        book = gncopen(args[0])
    except:
        sys.stderr.write("cannot open file '{0}'\n".format(args[0]))
        sys.exit(1)

    today = date.today()
    year, month = (today.year, today.month)
    year = len(args) >= 2 and args[1] or today.year
    month = len(args) >= 3 and args[2] or today.month
    if len(args) == 1:
        print book.monthly_income_stm(date.today().year)
    elif len(args) == 2:
        print book.monthly_income_stm(int(args[1]))
    else:
        year, month = (int(args[1]), int(args[2]))
        print book.income_stm(first_date_of_month(year, month),
                              last_date_of_month(year, month))

if __name__ == "__main__":
    main()
