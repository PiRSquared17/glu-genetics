# -*- coding: utf-8 -*-

from __future__ import division

__abstract__  = 'Forward and backward compatibility for various Python versions'
__copyright__ = 'Copyright (c) 2007-2009, BioInformed LLC and the U.S. Department of Health & Human Services. Funded by NCI under Contract N01-CO-12400.'
__license__   = 'See GLU license for terms by running: glu license'
__revision__  = '$Id$'

# The current contents of this module are backports (i.e., copies) of
# various Python 2.7 collections classes (namedtuple and Counter) for GLU
# running under Python 2.5 or 2.6.  Obviously, all credit goes to the Python
# core team for these shiny toys.  Note that the coding style has been
# maintained from the Python stdlib for ease of maintenance.


__all__ = []

import sys        as _sys
import heapq      as _heapq
import collections

from   operator  import itemgetter as _itemgetter
from   keyword   import iskeyword as _iskeyword
from   itertools import repeat as _repeat, starmap as _starmap, ifilter as _ifilter


if not hasattr(collections, 'namedtuple'):
    __all__ += ['namedtuple']

    def namedtuple(typename, field_names, verbose=False):
        """Returns a new subclass of tuple with named fields.

        >>> Point = namedtuple('Point', 'x y')
        >>> Point.__doc__                   # docstring for the new class
        'Point(x, y)'
        >>> p = Point(11, y=22)             # instantiate with positional args or keywords
        >>> p[0] + p[1]                     # indexable like a plain tuple
        33
        >>> x, y = p                        # unpack like a regular tuple
        >>> x, y
        (11, 22)
        >>> p.x + p.y                       # fields also accessable by name
        33
        >>> d = p._asdict()                 # convert to a dictionary
        >>> d['x']
        11
        >>> Point(**d)                      # convert from a dictionary
        Point(x=11, y=22)
        >>> p._replace(x=100)               # _replace() is like str.replace() but targets named fields
        Point(x=100, y=22)

        """

        # Parse and validate the field names.  Validation serves two purposes,
        # generating informative error messages and preventing template injection attacks.
        if isinstance(field_names, basestring):
            field_names = field_names.replace(',', ' ').split() # names separated by whitespace and/or commas
        field_names = tuple(map(str, field_names))
        for name in (typename,) + field_names:
            if not all(c.isalnum() or c=='_' for c in name):
                raise ValueError('Type names and field names can only contain alphanumeric characters and underscores: %r' % name)
            if _iskeyword(name):
                raise ValueError('Type names and field names cannot be a keyword: %r' % name)
            if name[0].isdigit():
                raise ValueError('Type names and field names cannot start with a number: %r' % name)
        seen_names = set()
        for name in field_names:
            if name.startswith('_'):
                raise ValueError('Field names cannot start with an underscore: %r' % name)
            if name in seen_names:
                raise ValueError('Encountered duplicate field name: %r' % name)
            seen_names.add(name)

        # Create and fill-in the class template
        numfields = len(field_names)
        argtxt = repr(field_names).replace("'", "")[1:-1]   # tuple repr without parens or quotes
        reprtxt = ', '.join('%s=%%r' % name for name in field_names)
        dicttxt = ', '.join('%r: t[%d]' % (name, pos) for pos, name in enumerate(field_names))
        template = '''class %(typename)s(tuple):
        '%(typename)s(%(argtxt)s)' \n
        __slots__ = () \n
        _fields = %(field_names)r \n
        def __new__(_cls, %(argtxt)s):
            return _tuple.__new__(_cls, (%(argtxt)s)) \n
        @classmethod
        def _make(cls, iterable, new=tuple.__new__, len=len):
            'Make a new %(typename)s object from a sequence or iterable'
            result = new(cls, iterable)
            if len(result) != %(numfields)d:
                raise TypeError('Expected %(numfields)d arguments, got %%d' %% len(result))
            return result \n
        def __repr__(self):
            return '%(typename)s(%(reprtxt)s)' %% self \n
        def _asdict(t):
            'Return a new dict which maps field names to their values'
            return {%(dicttxt)s} \n
        def _replace(_self, **kwds):
            'Return a new %(typename)s object replacing specified fields with new values'
            result = _self._make(map(kwds.pop, %(field_names)r, _self))
            if kwds:
                raise ValueError('Got unexpected field names: %%r' %% kwds.keys())
            return result \n
        def __getnewargs__(self):
            return tuple(self) \n\n''' % locals()
        for i, name in enumerate(field_names):
            template += '        %s = _property(_itemgetter(%d))\n' % (name, i)
        if verbose:
            print template

        # Execute the template string in a temporary namespace and
        # support tracing utilities by setting a value for frame.f_globals['__name__']
        namespace = dict(_itemgetter=_itemgetter, __name__='namedtuple_%s' % typename,
                         _property=property, _tuple=tuple)
        try:
            exec template in namespace
        except SyntaxError, e:
            raise SyntaxError(e.message + ':\n' + template)
        result = namespace[typename]

        # For pickling to work, the __module__ variable needs to be set to the frame
        # where the named tuple is created.  Bypass this step in enviroments where
        # sys._getframe is not defined (Jython for example).
        if hasattr(_sys, '_getframe'):
            result.__module__ = _sys._getframe(1).f_globals.get('__name__', '__main__')

        return result


########################################################################
###  Counter
########################################################################

if not hasattr(collections, 'Counter'):
    __all__ += ['Counter']

    Mapping = (dict,)


    def _chain_from_iterable(iterables):
        # chain.from_iterable(['ABC', 'DEF']) --> A B C D E F
        for it in iterables:
            for element in it:
                yield element


    class Counter(dict):
        '''Dict subclass for counting hashable items.  Sometimes called a bag
        or multiset.  Elements are stored as dictionary keys and their counts
        are stored as dictionary values.

        >>> c = Counter('abracadabra')      # count elements from a string

        >>> c.most_common(3)                # three most common elements
        [('a', 5), ('r', 2), ('b', 2)]
        >>> sorted(c)                       # list all unique elements
        ['a', 'b', 'c', 'd', 'r']
        >>> ''.join(sorted(c.elements()))   # list elements with repetitions
        'aaaaabbcdrr'
        >>> sum(c.values())                 # total of all counts
        11

        >>> c['a']                          # count of letter 'a'
        5
        >>> for elem in 'shazam':           # update counts from an iterable
        ...     c[elem] += 1                # by adding 1 to each element's count
        >>> c['a']                          # now there are seven 'a'
        7
        >>> del c['r']                      # remove all 'r'
        >>> c['r']                          # now there are zero 'r'
        0

        >>> d = Counter('simsalabim')       # make another counter
        >>> c.update(d)                     # add in the second counter
        >>> c['a']                          # now there are nine 'a'
        9

        >>> c.clear()                       # empty the counter
        >>> c
        Counter()

        Note:  If a count is set to zero or reduced to zero, it will remain
        in the counter until the entry is deleted or the counter is cleared:

        >>> c = Counter('aaabbc')
        >>> c['b'] -= 2                     # reduce the count of 'b' by two
        >>> c.most_common()                 # 'b' is still in, but its count is zero
        [('a', 3), ('c', 1), ('b', 0)]

        '''
        # References:
        #   http://en.wikipedia.org/wiki/Multiset
        #   http://www.gnu.org/software/smalltalk/manual-base/html_node/Bag.html
        #   http://www.demo2s.com/Tutorial/Cpp/0380__set-multiset/Catalog0380__set-multiset.htm
        #   http://code.activestate.com/recipes/259174/
        #   Knuth, TAOCP Vol. II section 4.6.3

        def __init__(self, iterable=None, **kwds):
            '''Create a new, empty Counter object.  And if given, count elements
            from an input iterable.  Or, initialize the count from another mapping
            of elements to their counts.

            >>> c = Counter()                           # a new, empty counter
            >>> c = Counter('gallahad')                 # a new counter from an iterable
            >>> c = Counter({'a': 4, 'b': 2})           # a new counter from a mapping
            >>> c = Counter(a=4, b=2)                   # a new counter from keyword args

            '''
            self.update(iterable, **kwds)

        def __missing__(self, key):
            'The count of elements not in the Counter is zero.'
            # Needed so that self[missing_item] does not raise KeyError
            return 0

        def most_common(self, n=None):
            '''List the n most common elements and their counts from the most
            common to the least.  If n is None, then list all element counts.

            >>> Counter('abracadabra').most_common(3)
            [('a', 5), ('r', 2), ('b', 2)]

            '''
            # Emulate Bag.sortedByCount from Smalltalk
            if n is None:
                return sorted(self.iteritems(), key=_itemgetter(1), reverse=True)
            return _heapq.nlargest(n, self.iteritems(), key=_itemgetter(1))

        def elements(self):
            '''Iterator over elements repeating each as many times as its count.

            >>> c = Counter('ABCABC')
            >>> sorted(c.elements())
            ['A', 'A', 'B', 'B', 'C', 'C']

            # Knuth's example for prime factors of 1836:  2**2 * 3**3 * 17**1
            >>> prime_factors = Counter({2: 2, 3: 3, 17: 1})
            >>> product = 1
            >>> for factor in prime_factors.elements():     # loop over factors
            ...     product *= factor                       # and multiply them
            >>> product
            1836

            Note, if an element's count has been set to zero or is a negative
            number, elements() will ignore it.

            '''
            # Emulate Bag.do from Smalltalk and Multiset.begin from C++.
            return _chain_from_iterable(_starmap(_repeat, self.iteritems()))

        # Override dict methods where necessary

        @classmethod
        def fromkeys(cls, iterable, v=None):
            # There is no equivalent method for counters because setting v=1
            # means that no element can have a count greater than one.
            raise NotImplementedError(
                'Counter.fromkeys() is undefined.  Use Counter(iterable) instead.')

        def update(self, iterable=None, **kwds):
            '''Like dict.update() but add counts instead of replacing them.

            Source can be an iterable, a dictionary, or another Counter instance.

            >>> c = Counter('which')
            >>> c.update('witch')           # add elements from another iterable
            >>> d = Counter('watch')
            >>> c.update(d)                 # add elements from another counter
            >>> c['h']                      # four 'h' in which, witch, and watch
            4

            '''
            # The regular dict.update() operation makes no sense here because the
            # replace behavior results in the some of original untouched counts
            # being mixed-in with all of the other counts for a mismash that
            # doesn't have a straight-forward interpretation in most counting
            # contexts.  Instead, we implement straight-addition.  Both the inputs
            # and outputs are allowed to contain zero and negative counts.

            if iterable is not None:
                if isinstance(iterable, Mapping):
                    if self:
                        self_get = self.get
                        for elem, count in iterable.iteritems():
                            self[elem] = self_get(elem, 0) + count
                    else:
                        dict.update(self, iterable) # fast path when counter is empty
                else:
                    self_get = self.get
                    for elem in iterable:
                        self[elem] = self_get(elem, 0) + 1
            if kwds:
                self.update(kwds)

        def copy(self):
            'Like dict.copy() but returns a Counter instance instead of a dict.'
            return Counter(self)

        def __delitem__(self, elem):
            'Like dict.__delitem__() but does not raise KeyError for missing values.'
            if elem in self:
                dict.__delitem__(self, elem)

        def __repr__(self):
            if not self:
                return '%s()' % self.__class__.__name__
            items = ', '.join(map('%r: %r'.__mod__, self.most_common()))
            return '%s({%s})' % (self.__class__.__name__, items)

        # Multiset-style mathematical operations discussed in:
        #       Knuth TAOCP Volume II section 4.6.3 exercise 19
        #       and at http://en.wikipedia.org/wiki/Multiset
        #
        # Outputs guaranteed to only include positive counts.
        #
        # To strip negative and zero counts, add-in an empty counter:
        #       c += Counter()

        def __add__(self, other):
            '''Add counts from two counters.

            >>> Counter('abbb') + Counter('bcc')
            Counter({'b': 4, 'c': 2, 'a': 1})

            '''
            if not isinstance(other, Counter):
                return NotImplemented
            result = Counter()
            for elem in set(self) | set(other):
                newcount = self[elem] + other[elem]
                if newcount > 0:
                    result[elem] = newcount
            return result

        def __sub__(self, other):
            ''' Subtract count, but keep only results with positive counts.

            >>> Counter('abbbc') - Counter('bccd')
            Counter({'b': 2, 'a': 1})

            '''
            if not isinstance(other, Counter):
                return NotImplemented
            result = Counter()
            for elem in set(self) | set(other):
                newcount = self[elem] - other[elem]
                if newcount > 0:
                    result[elem] = newcount
            return result

        def __or__(self, other):
            '''Union is the maximum of value in either of the input counters.

            >>> Counter('abbb') | Counter('bcc')
            Counter({'b': 3, 'c': 2, 'a': 1})

            '''
            if not isinstance(other, Counter):
                return NotImplemented
            result = Counter()
            for elem in set(self) | set(other):
                p, q = self[elem], other[elem]
                newcount = q if p < q else p
                if newcount > 0:
                    result[elem] = newcount
            return result

        def __and__(self, other):
            ''' Intersection is the minimum of corresponding counts.

            >>> Counter('abbb') & Counter('bcc')
            Counter({'b': 1})

            '''
            if not isinstance(other, Counter):
                return NotImplemented
            result = Counter()
            if len(self) < len(other):
                self, other = other, self
            for elem in _ifilter(self.__contains__, other):
                p, q = self[elem], other[elem]
                newcount = p if p < q else q
                if newcount > 0:
                    result[elem] = newcount
            return result


def _test():
    import doctest
    return doctest.testmod()


if __name__ == '__main__':
    _test()